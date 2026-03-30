import sys, os, subprocess, threading, time, sqlite3, configparser, webbrowser, ctypes, socket, hashlib, textwrap
from PyQt5.QtCore import QTimer, QEvent, Qt, pyqtSignal, QObject
from datetime import datetime
from croniter import croniter
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QLabel,
                             QGridLayout, QLineEdit, QTableWidget, QTableWidgetItem, QCheckBox,
                             QComboBox, QMessageBox, QInputDialog,
                             QSystemTrayIcon, QMenu, QAction, QStyle, QDialog, QHBoxLayout)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt

if getattr(sys, 'frozen', False):
    # Lokasi folder tempat file .exe berada (untuk DB, INI, dan folder server)
    BASE_PATH = os.path.dirname(sys.executable)
    # Path internal bundle khusus untuk resource yang di-embed (seperti icon)
    BUNDLE_PATH = getattr(sys, '_MEIPASS', BASE_PATH)
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_PATH = BASE_PATH

DB_PATH = os.path.join(BASE_PATH, "setting.db")
INI_PATH = os.path.join(BASE_PATH, "localization.ini")

APACHE_PATH = os.path.join(BASE_PATH, "apache", "bin", "httpd.exe")
MYSQL_PATH = os.path.join(BASE_PATH, "mysql", "bin", "mysqld.exe")
REDIS_PATH = os.path.join(BASE_PATH, "redis", "redis-server.exe")

db_lock = threading.RLock() # Re-entrant lock untuk mencegah deadlock pada nested calls

class LogSignal(QObject):
    updated = pyqtSignal()

log_signal = LogSignal()

# --- Localization ---
config = configparser.ConfigParser()
config.read(INI_PATH, encoding='utf-8')

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(('127.0.0.1', port)) == 0

def replace_and_write(template_name, target_path):
    template_path = os.path.join(BASE_PATH, "config", template_name)
    if not os.path.exists(template_path):
        add_log(f"Template not found: {template_path}", "WARNING")
        return
    
    try:
        with open(template_path, "r", encoding='utf-8') as f:
            content = f.read()
        
        # Replace ${INSTALL_DIR} dengan BASE_PATH (menggunakan forward slash untuk config)
        clean_base = BASE_PATH.replace("\\", "/")
        content = content.replace("{ROOT}", clean_base)
        content = content.replace("${INSTALL_DIR}", clean_base)
        content = content.replace("{APACHE_PORT}", get_setting('apache_port', '80'))
        content = content.replace("{MYSQL_PORT}", get_setting('mysql_port', '3306'))
        content = content.replace("{REDIS_PORT}", get_setting('redis_port', '6379'))
        
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding='utf-8') as f:
            f.write(content)
        add_log(f"Generated config: {os.path.basename(target_path)}")
    except Exception as e:
        add_log(f"Error generating config {template_name}: {str(e)}", "ERROR")

def prepare_environment():
    add_log("Preparing environment directories and configs...")
    # Create Directories
    dirs = ["www", "tmp", "data", "data/mysql", "data/redis", "logs", "sessions", "apache/logs"]
    for d in dirs:
        os.makedirs(os.path.join(BASE_PATH, d), exist_ok=True)
    
    # Generate Configs from Templates
    replace_and_write("httpd-template.conf", os.path.join(BASE_PATH, "config", "httpd.conf"))
    replace_and_write("php-template.ini", os.path.join(BASE_PATH, "php", "php.ini"))
    replace_and_write("my-template.ini", os.path.join(BASE_PATH, "config", "my.ini"))
    replace_and_write("redis.windows-template.conf", os.path.join(BASE_PATH, "redis", "redis.windows.conf"))

    # Update PATH for PHP
    php_path = os.path.join(BASE_PATH, "php")
    php_ext = os.path.join(BASE_PATH, "php", "ext")
    env_path = os.environ.get("PATH", "")
    if php_path not in env_path:
        os.environ["PATH"] = f"{php_path}{os.pathsep}{php_ext}{os.pathsep}{env_path}"

def set_run_on_startup(enabled):
    if os.name != 'nt': return
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "PortableServerPanel"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enabled:
            cmd = f'"{sys.executable}"' if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{os.path.abspath(__file__)}"'
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass

def get_languages():
    return config.sections()

def tr(lang, key):
    if lang in config and key in config[lang]:
        return config[lang][key]
    return key

# --- Database setup ---
def init_db():
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cron_expr TEXT NOT NULL,
            command TEXT NOT NULL,
            enabled INTEGER DEFAULT 1
        )""")
        try:
            cur.execute("ALTER TABLE jobs ADD COLUMN enabled INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass

        cur.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL
        )""")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('start_minimized', '0')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('language', 'en')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('run_on_startup', '0')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_start_services', '0')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('window_width', '800')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('window_height', '600')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('window_maximized', '0')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('apache_access_mode', 'external')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('mysql_access_mode', 'external')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('redis_access_mode', 'external')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('apache_port', '80')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('mysql_port', '3306')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('redis_port', '6379')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('mariadb_installed', '0')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('apache_pid', '0')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('mysql_pid', '0')")
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('redis_pid', '0')")
        conn.commit()
        conn.close()

    prepare_environment()
    set_apache_access(get_setting('apache_access_mode', 'local') == 'external', force=True)
    set_mysql_access(get_setting('mysql_access_mode', 'local') == 'external', force=True)
    set_redis_access(get_setting('redis_access_mode', 'local') == 'external', force=True)

def add_log(message, level="INFO"):
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)", (ts, level, message))
        conn.commit()
        conn.close()
        log_signal.updated.emit()

def get_setting(key, default='0'):
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        conn.close()
    return row[0] if row else default

def set_setting(key, value):
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()

# --- Scheduler thread ---
def scheduler_loop():
    while True:
        # Sinkronisasi: Tunggu hingga detik 00 pada menit berikutnya berdasarkan system clock
        now_ts = time.time()
        wait_time = 60 - (now_ts % 60)
        # Tambahkan offset kecil (0.1 detik) untuk memastikan transisi menit sudah sempurna
        time.sleep(wait_time + 0.1)

        # Ambil waktu saat ini dengan presisi menit (detik dan mikrodetik diabaikan)
        current_time = datetime.now().replace(second=0, microsecond=0)
        
        try:
            with db_lock:
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("SELECT cron_expr, command FROM jobs WHERE enabled=1")
                jobs_in_memory = cur.fetchall()
                conn.close()

            for cron_expr, command in jobs_in_memory:
                # Skip job jika command kosong atau hanya berisi spasi
                if not command or not command.strip():
                    continue
                try:
                    # Periksa apakah pattern cron cocok dengan waktu menit ini
                    if croniter.match(cron_expr, current_time):
                        # Jalankan task tanpa memunculkan window console (penting untuk script PHP/Background task)
                        subprocess.Popen(command, shell=True,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception as e:
                    # Abaikan error pada pattern tertentu agar loop tetap berjalan
                    pass
        except Exception as e:
            add_log(f"Scheduler loop error: {str(e)}", "ERROR")

# --- Access control (edit config files) ---
def set_apache_access(external=False, force=False):
    new_mode = 'external' if external else 'local'
    if not force and get_setting('apache_access_mode') == new_mode:
        return
    conf_path = os.path.join(BASE_PATH, "config", "httpd.conf")
    port = get_setting('apache_port', '80')
    if os.path.exists(conf_path):
        with open(conf_path, "r", encoding='utf-8') as f:
            lines = f.readlines()
        with open(conf_path, "w", encoding='utf-8') as f:
            for line in lines:
                if line.strip().startswith("Listen"):
                    f.write(f"Listen 0.0.0.0:{port}\n" if external else f"Listen 127.0.0.1:{port}\n")
                else:
                    f.write(line)
        set_setting('apache_access_mode', new_mode)
        add_log(f"Apache access mode changed to {'Online' if external else 'Offline'}")

def set_mysql_access(external=False, force=False):
    new_mode = 'external' if external else 'local'
    if not force and get_setting('mysql_access_mode') == new_mode:
        return
    conf_path = os.path.join(BASE_PATH, "config", "my.ini")
    port = get_setting('mysql_port', '3306')
    if os.path.exists(conf_path):
        with open(conf_path, "r", encoding='utf-8') as f:
            lines = f.readlines()
        
        new_val = "0.0.0.0" if external else "127.0.0.1"
        found = False
        new_lines = []
        for line in lines:
            if line.strip().startswith("bind-address"):
                new_lines.append(f"bind-address={new_val}\n")
                found = True
            elif line.strip().startswith("port="):
                new_lines.append(f"port={port}\n")
            else:
                new_lines.append(line)
        
        if not found:
            # Jika tidak ditemukan, sisipkan di bawah section [mysqld]
            final_lines = []
            for line in new_lines:
                final_lines.append(line)
                if "[mysqld]" in line:
                    final_lines.append(f"bind-address={new_val}\n")
                    found = True
            new_lines = final_lines if found else new_lines + [f"\n[mysqld]\nbind-address={new_val}\n"]

        set_setting('mysql_access_mode', new_mode)
        with open(conf_path, "w", encoding='utf-8') as f:
            f.writelines(new_lines)
        add_log(f"MariaDB access mode changed to {'Online' if external else 'Offline'}")

def set_redis_access(external=False, force=False):
    new_mode = 'external' if external else 'local'
    if not force and get_setting('redis_access_mode') == new_mode:
        return
    conf_path = os.path.join(BASE_PATH, "redis", "redis.windows.conf")
    port = get_setting('redis_port', '6379')
    if os.path.exists(conf_path):
        with open(conf_path, "r", encoding='utf-8') as f:
            lines = f.readlines()
        with open(conf_path, "w", encoding='utf-8') as f:
            for line in lines:
                if line.strip().startswith("bind"):
                    f.write("bind 0.0.0.0\n" if external else "bind 127.0.0.1\n")
                elif line.strip().startswith("port "):
                    f.write(f"port {port}\n")
                else:
                    f.write(line)
        set_setting('redis_access_mode', new_mode)
        add_log(f"Redis access mode changed to {'Online' if external else 'Offline'}")

class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle(tr(parent.current_lang, "settings_title"))
        self.setModal(True)
        self.resize(300, 200)
        
        layout = QGridLayout()
        
        layout.addWidget(QLabel(tr(parent.current_lang, "lbl_apache_port")), 0, 0)
        self.apache_port = QLineEdit(get_setting('apache_port', '80'))
        self.apache_port.setToolTip(tr(parent.current_lang, "help_apache_port"))
        layout.addWidget(self.apache_port, 0, 1)
        
        layout.addWidget(QLabel(tr(parent.current_lang, "lbl_mysql_port")), 1, 0)
        self.mysql_port = QLineEdit(get_setting('mysql_port', '3306'))
        self.mysql_port.setToolTip(tr(parent.current_lang, "help_mysql_port"))
        layout.addWidget(self.mysql_port, 1, 1)
        
        layout.addWidget(QLabel(tr(parent.current_lang, "lbl_redis_port")), 2, 0)
        self.redis_port = QLineEdit(get_setting('redis_port', '6379'))
        self.redis_port.setToolTip(tr(parent.current_lang, "help_redis_port"))
        layout.addWidget(self.redis_port, 2, 1)
        
        self.btn_save = QPushButton(tr(parent.current_lang, "btn_save"))
        self.btn_save.clicked.connect(self.save)
        layout.addWidget(self.btn_save, 3, 0, 1, 2)
        
        self.setLayout(layout)
        direction = self.parent.get_lang_dir(self.parent.current_lang)
        self.setLayoutDirection(Qt.RightToLeft if direction == 'rtl' else Qt.LeftToRight)
        
    def save(self):
        set_setting('apache_port', self.apache_port.text())
        set_setting('mysql_port', self.mysql_port.text())
        set_setting('redis_port', self.redis_port.text())
        self.parent.apply_port_settings()
        self.accept()

class SchedulerDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle(tr(parent.current_lang, "scheduler_title"))
        self.setModal(True)
        self.resize(600, 450)
        
        layout = QGridLayout()
        
        layout.addWidget(QLabel(tr(parent.current_lang, "col_cron")), 0, 0)
        self.cron_input = QLineEdit("*/1 * * * *")
        layout.addWidget(self.cron_input, 0, 1)
        
        layout.addWidget(QLabel(tr(parent.current_lang, "col_cmd")), 1, 0)
        self.cmd_input = QLineEdit("")
        layout.addWidget(self.cmd_input, 1, 1)
        
        self.chk_enabled = QCheckBox(tr(parent.current_lang, "lbl_enabled"))
        self.chk_enabled.setChecked(True)
        layout.addWidget(self.chk_enabled, 2, 1)
        
        self.btn_add = QPushButton(tr(parent.current_lang, "btn_add_job"))
        self.btn_add.clicked.connect(self.add_job)
        layout.addWidget(self.btn_add, 3, 0, 1, 2)
        
        self.job_table = QTableWidget()
        self.job_table.setColumnCount(4)
        self.job_table.setHorizontalHeaderLabels([
            tr(parent.current_lang, "col_id"),
            tr(parent.current_lang, "col_cron"),
            tr(parent.current_lang, "col_cmd"),
            tr(parent.current_lang, "col_enabled")
        ])
        self.job_table.itemClicked.connect(self.on_item_clicked)
        layout.addWidget(self.job_table, 4, 0, 1, 2)
        
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_edit = QPushButton(tr(parent.current_lang, "btn_edit_job"))
        self.btn_edit.clicked.connect(self.edit_job)
        btn_layout.addWidget(self.btn_edit, 2) # Perbandingan lebar 2
        
        self.btn_delete = QPushButton(tr(parent.current_lang, "btn_delete_job"))
        self.btn_delete.clicked.connect(self.delete_job)
        btn_layout.addWidget(self.btn_delete, 1) # Perbandingan lebar 1
        layout.addLayout(btn_layout, 5, 0, 1, 2)

        self.setLayout(layout)
        self.load_jobs()
        direction = self.parent.get_lang_dir(self.parent.current_lang)
        self.setLayoutDirection(Qt.RightToLeft if direction == 'rtl' else Qt.LeftToRight)

    def on_item_clicked(self, item):
        row = item.row()
        self.cron_input.setText(self.job_table.item(row, 1).text())
        self.cmd_input.setText(self.job_table.item(row, 2).text())
        status = self.job_table.item(row, 3).text()
        self.chk_enabled.setChecked(status == tr(self.parent.current_lang, "status_enabled"))

    def load_jobs(self):
        self.job_table.setRowCount(0)
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT id, cron_expr, command, enabled FROM jobs")
            jobs = cur.fetchall()
            conn.close()
            
        for row_data in jobs:
            row_num = self.job_table.rowCount()
            self.job_table.insertRow(row_num)
            for i, data in enumerate(row_data):
                val = str(data)
                if i == 3: val = tr(self.parent.current_lang, "status_enabled") if data == 1 else tr(self.parent.current_lang, "status_disabled")
                self.job_table.setItem(row_num, i, QTableWidgetItem(val))
        conn.close()
        self.job_table.resizeColumnsToContents()

    def add_job(self):
        cron = self.cron_input.text().strip()
        cmd = self.cmd_input.text().strip()
        if not cron:
            QMessageBox.warning(self, "Error", tr(self.parent.current_lang, "msg_cron_empty"))
            return
        if not cmd:
            QMessageBox.warning(self, "Error", tr(self.parent.current_lang, "msg_command_empty"))
            return

        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("INSERT INTO jobs (cron_expr, command, enabled) VALUES (?, ?, ?)", 
                        (cron, cmd, 1 if self.chk_enabled.isChecked() else 0))
            conn.commit()
            conn.close()
        self.load_jobs()

    def edit_job(self):
        curr = self.job_table.currentRow()
        if curr >= 0:
            cron = self.cron_input.text().strip()
            cmd = self.cmd_input.text().strip()
            if not cron:
                QMessageBox.warning(self, "Error", tr(self.parent.current_lang, "msg_cron_empty"))
                return
            if not cmd:
                QMessageBox.warning(self, "Error", tr(self.parent.current_lang, "msg_command_empty"))
                return

            job_id = self.job_table.item(curr, 0).text()
            with db_lock:
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("UPDATE jobs SET cron_expr=?, command=?, enabled=? WHERE id=?", 
                            (cron, cmd, 1 if self.chk_enabled.isChecked() else 0, job_id))
                conn.commit()
                conn.close()
            self.load_jobs()

    def delete_job(self):
        curr = self.job_table.currentRow()
        if curr >= 0:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Question)
            msg.setWindowTitle(tr(self.parent.current_lang, "confirm_delete_title"))
            msg.setText(tr(self.parent.current_lang, "confirm_delete_msg"))
            btn_yes = msg.addButton(tr(self.parent.current_lang, "btn_yes"), QMessageBox.YesRole)
            btn_no = msg.addButton(tr(self.parent.current_lang, "btn_no"), QMessageBox.NoRole)
            msg.setDefaultButton(btn_no)
            msg.exec_()
            if msg.clickedButton() == btn_yes:
                job_id = self.job_table.item(curr, 0).text()
                with db_lock:
                    conn = sqlite3.connect(DB_PATH)
                    cur = conn.cursor()
                    cur.execute("DELETE FROM jobs WHERE id=?", (job_id,))
                    conn.commit()
                    conn.close()
                self.load_jobs()

class MariaDBPasswordDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle(tr(parent.current_lang, "db_password_title"))
        self.setModal(True)
        self.resize(350, 200)
        
        layout = QGridLayout()
        
        layout.addWidget(QLabel(tr(parent.current_lang, "lbl_current_password")), 0, 0)
        self.current_pass_input = QLineEdit()
        self.current_pass_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.current_pass_input, 0, 1)
        
        layout.addWidget(QLabel(tr(parent.current_lang, "lbl_new_password")), 1, 0)
        self.new_pass_input = QLineEdit()
        self.new_pass_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.new_pass_input, 1, 1)
        
        layout.addWidget(QLabel(tr(parent.current_lang, "lbl_repeat_password")), 2, 0)
        self.repeat_pass_input = QLineEdit()
        self.repeat_pass_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.repeat_pass_input, 2, 1)
        
        self.chk_force_reset = QCheckBox(tr(parent.current_lang, "chk_force_reset"))
        layout.addWidget(self.chk_force_reset, 3, 1)
        
        self.btn_change = QPushButton(tr(parent.current_lang, "btn_change_password"))
        self.btn_change.clicked.connect(self.change_password)
        layout.addWidget(self.btn_change, 4, 0, 1, 2)
        
        self.setLayout(layout)
        direction = self.parent.get_lang_dir(self.parent.current_lang)
        self.setLayoutDirection(Qt.RightToLeft if direction == 'rtl' else Qt.LeftToRight)

    def change_password(self):
        # 1. Ambil input dan bersihkan spasi jika perlu
        curr_pass = self.current_pass_input.text()
        new_pass = self.new_pass_input.text()
        repeat_pass = self.repeat_pass_input.text()
        force = self.chk_force_reset.isChecked()
        lang = self.parent.current_lang

        # 2. Validasi Dasar
        if not new_pass:
            QMessageBox.warning(self, tr(lang, "error_title"), tr(lang, "msg_new_password_can_not_be_empty"))
            return

        if new_pass != repeat_pass:
            QMessageBox.warning(self, tr(lang, "error_title"), tr(lang, "msg_password_mismatch"))
            return

        # Escape single quotes untuk keamanan SQL manual
        # Ini mencegah password seperti "Jum'at" merusak query
        escaped_pass = new_pass.replace("'", "''")

        if force:
            # Security Check for Force Reset
            admin_hash = get_setting('admin_password_hash', '')
            
            if not admin_hash:
                # Setup new admin password if not exists
                msg = textwrap.fill(tr(lang, "msg_setup_admin_pass"), width=55)
                ans, ok = QInputDialog.getText(self, tr(lang, "lbl_admin_password_setup"), 
                                              msg, QLineEdit.Password)
                if ok and ans:
                    hashed = hashlib.sha256(ans.encode()).hexdigest()
                    set_setting('admin_password_hash', hashed)
                    QMessageBox.information(self, tr(lang, "success_title"), tr(lang, "msg_admin_password_created"))
                else:
                    # User cancelled or empty
                    if ok: QMessageBox.warning(self, tr(lang, "error_title"), tr(lang, "msg_new_password_can_not_be_empty"))
                    return
            else:
                # Verify existing admin password
                msg = textwrap.fill(tr(lang, "msg_enter_admin_pass"), width=55)
                ans, ok = QInputDialog.getText(self, tr(lang, "lbl_admin_password_verify"), 
                                              msg, QLineEdit.Password)
                if ok:
                    input_hash = hashlib.sha256(ans.encode()).hexdigest()
                    if input_hash != admin_hash:
                        QMessageBox.warning(self, tr(lang, "error_title"), tr(lang, "msg_admin_pass_wrong"))
                        return
                else:
                    return

            self.parent.stop_service("mysql")
            time.sleep(1)
            
            init_file = os.path.join(BASE_PATH, "tmp", "reset_pass.sql")
            os.makedirs(os.path.dirname(init_file), exist_ok=True)
            
            # Gunakan FLUSH PRIVILEGES agar perubahan langsung terbaca
            sql_cmd = f"FLUSH PRIVILEGES;\nALTER USER 'root'@'localhost' IDENTIFIED BY '{escaped_pass}';\n"
            
            try:
                # Gunakan encoding utf-8 agar mendukung password non-ASCII jika user memaksa
                with open(init_file, "w", encoding='utf-8') as f:
                    f.write(sql_cmd)
                
                conf = os.path.join(BASE_PATH, "config", "my.ini")
                # Tambahkan --skip-grant-tables jika perlu, tapi --init-file biasanya sudah cukup
                args = [MYSQL_PATH, f"--defaults-file={conf}", f"--init-file={init_file}", "--console"]
                
                proc = subprocess.Popen(args, cwd=os.path.join(BASE_PATH, "mysql"), 
                                       creationflags=subprocess.CREATE_NO_WINDOW)
                
                # Beri waktu sedikit lebih lama agar MariaDB benar-benar siap
                time.sleep(3) 
                
                # Matikan proses sementara tadi
                subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, 
                               creationflags=subprocess.CREATE_NO_WINDOW)
                
                if os.path.exists(init_file):
                    os.remove(init_file)
                
                QMessageBox.information(self, tr(lang, "success_title"), tr(lang, "msg_password_changed_success"))
                self.accept()
            except Exception as e:
                add_log(f"Force reset failed: {str(e)}", "ERROR")
                QMessageBox.critical(self, tr(lang, "error_title"), f"{tr(lang, 'msg_password_change_failed')}\n{str(e)}")
        else:
            # Standard change logic
            client_path = os.path.join(BASE_PATH, "mysql", "bin", "mariadb.exe")
            if not os.path.exists(client_path):
                client_path = os.path.join(BASE_PATH, "mysql", "bin", "mysql.exe")
                
            if not os.path.exists(client_path):
                QMessageBox.critical(self, tr(lang, "error_title"), "MariaDB client not found.")
                return

            # Gunakan subprocess.run dengan input untuk keamanan (menghindari pass di argumen CMD)
            sql = f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{escaped_pass}';"
            cmd = [client_path, "-u", "root"]
            if curr_pass:
                # Menempelkan password ke -p (misal -proot123)
                cmd.append(f"-p{curr_pass}")
            
            cmd.extend(["-e", sql])
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, 
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode == 0:
                    QMessageBox.information(self, tr(lang, "success_title"), tr(lang, "msg_password_changed_success"))
                    self.accept()
                else:
                    err = result.stderr.lower()
                    if "access denied" in err:
                        QMessageBox.warning(self, tr(lang, "error_title"), tr(lang, "msg_current_password_wrong"))
                    else:
                        QMessageBox.critical(self, tr(lang, "error_title"), f"{tr(lang, 'msg_password_change_failed')}\n{result.stderr}")
            except Exception as e:
                QMessageBox.critical(self, tr(lang, "error_title"), f"{tr(lang, 'msg_password_change_failed')}\n{str(e)}")

class ControlPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Server Control Panel")
        self.move(100, 100)
        width = int(get_setting('window_width', '800'))
        height = int(get_setting('window_height', '600'))
        self.resize(width, height)

        if get_setting('window_maximized', '0') == '1':
            self.setWindowState(Qt.WindowMaximized)

        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.save_window_size)
        
        # Tombol Apache (Gunakan satu tombol untuk Start/Stop)
        self.btn_apache_toggle = QPushButton()
        self.btn_apache_toggle.clicked.connect(lambda: self.toggle_service_action("apache", APACHE_PATH))
        self.btn_apache_access_toggle = QPushButton()
        self.btn_apache_access_toggle.clicked.connect(lambda: self.toggle_access_action("apache"))

        # MySQL
        self.btn_mysql_toggle = QPushButton()
        self.btn_mysql_toggle.clicked.connect(lambda: self.toggle_service_action("mysql", MYSQL_PATH))
        self.btn_mysql_access_toggle = QPushButton()
        self.btn_mysql_access_toggle.clicked.connect(lambda: self.toggle_access_action("mysql"))

        # Redis
        self.btn_redis_toggle = QPushButton()
        self.btn_redis_toggle.clicked.connect(lambda: self.toggle_service_action("redis", REDIS_PATH))
        self.btn_redis_access_toggle = QPushButton()
        self.btn_redis_access_toggle.clicked.connect(lambda: self.toggle_access_action("redis"))

        # Menu for Apache Configuration Dropdown
        self.apache_config_menu = QMenu(self)
        self.action_httpd_conf = QAction("httpd.conf", self)
        self.action_httpd_conf.triggered.connect(lambda: self.open_config("apache"))
        self.action_php_ini = QAction("php.ini", self)
        self.action_php_ini.triggered.connect(lambda: self.open_config("php"))
        self.apache_config_menu.addAction(self.action_httpd_conf)
        self.apache_config_menu.addAction(self.action_php_ini)

        # Tambahkan padding horizontal agar caption tidak menyentuh tepi tombol
        self.setStyleSheet("""
            QPushButton {
                padding-left: 15px;
                padding-right: 15px;
                min-height: 25px;
            }

            QComboBox, QLineEdit {
                padding-left: 8px;
                padding-right: 8px;
                min-height: 25px;
            }
        """)

        # Set Window Icon
        icon_path = os.path.join(BUNDLE_PATH, "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.current_lang = get_setting('language', 'en')

        self.apply_layout_direction()

        # System Tray Icon

        maximize_path = os.path.join(BUNDLE_PATH, "maximize.png")
        self.tray_icon = QSystemTrayIcon(self)
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        
        self.tray_menu = QMenu()
        self.show_action = QAction("", self)
        if os.path.exists(maximize_path):
            self.show_action.setIcon(QIcon(maximize_path))
        self.show_action.triggered.connect(self.restore_from_tray)

        minimize_path = os.path.join(BUNDLE_PATH, "minimize.png")
        self.minimize_action = QAction("", self)
        if os.path.exists(minimize_path):
            self.minimize_action.setIcon(QIcon(minimize_path))
        self.minimize_action.triggered.connect(self.hide_to_tray)

        # Actions for All Services
        self.start_all_action = QAction("", self)
        start_icon = os.path.join(BUNDLE_PATH, "start.png")
        self.start_all_action.setIcon(QIcon(start_icon) if os.path.exists(start_icon) else self.style().standardIcon(QStyle.SP_MediaPlay))
        self.start_all_action.triggered.connect(self.start_all_services)

        self.stop_all_action = QAction("", self)
        stop_icon = os.path.join(BUNDLE_PATH, "stop.png")
        self.stop_all_action.setIcon(QIcon(stop_icon) if os.path.exists(stop_icon) else self.style().standardIcon(QStyle.SP_MediaStop))
        self.stop_all_action.triggered.connect(self.stop_all_services)

        self.online_all_action = QAction("", self)
        online_icon = os.path.join(BUNDLE_PATH, "public.png")
        self.online_all_action.setIcon(QIcon(online_icon) if os.path.exists(online_icon) else self.style().standardIcon(QStyle.SP_DriveNetIcon))
        self.online_all_action.triggered.connect(self.set_all_online)

        self.offline_all_action = QAction("", self)
        offline_icon = os.path.join(BUNDLE_PATH, "local.png")
        self.offline_all_action.setIcon(QIcon(offline_icon) if os.path.exists(offline_icon) else self.style().standardIcon(QStyle.SP_DriveHDIcon))
        self.offline_all_action.triggered.connect(self.set_all_offline)

        self.exit_action = QAction("", self)
        # Gunakan exit.png jika tersedia, jika tidak gunakan icon standar sistem
        exit_icon_path = os.path.join(BUNDLE_PATH, "exit.png")
        if os.path.exists(exit_icon_path):
            self.exit_action.setIcon(QIcon(exit_icon_path))
        else:
            self.exit_action.setIcon(self.style().standardIcon(QStyle.SP_DialogCloseButton))
        self.exit_action.triggered.connect(QApplication.instance().quit)
        
        self.tray_menu.addAction(self.show_action)
        self.tray_menu.addAction(self.minimize_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.start_all_action)
        self.tray_menu.addAction(self.stop_all_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.online_all_action)
        self.tray_menu.addAction(self.offline_all_action)
        self.tray_menu.addSeparator()

        # Individual Service Menus in Tray (Toggle Support)
        self.apache_tray_menu = self.tray_menu.addMenu("Apache")
        apache_icon_path = os.path.join(BUNDLE_PATH, "apache.png")
        if os.path.exists(apache_icon_path):
            self.apache_tray_menu.setIcon(QIcon(apache_icon_path))
        self.apache_tray_run = QAction("", self)
        self.apache_tray_run.triggered.connect(lambda: self.toggle_service_action("apache", APACHE_PATH))
        self.apache_tray_access = QAction("", self)
        self.apache_tray_access.triggered.connect(lambda: self.toggle_access_action("apache"))
        self.apache_tray_menu.addAction(self.apache_tray_run)
        self.apache_tray_menu.addAction(self.apache_tray_access)

        self.mysql_tray_menu = self.tray_menu.addMenu("MariaDB")
        mariadb_icon_path = os.path.join(BUNDLE_PATH, "mariadb.png")
        if os.path.exists(mariadb_icon_path):
            self.mysql_tray_menu.setIcon(QIcon(mariadb_icon_path))
        self.mysql_tray_run = QAction("", self)
        self.mysql_tray_run.triggered.connect(lambda: self.toggle_service_action("mysql", MYSQL_PATH))
        self.mysql_tray_access = QAction("", self)
        self.mysql_tray_access.triggered.connect(lambda: self.toggle_access_action("mysql"))
        self.mysql_tray_menu.addAction(self.mysql_tray_run)
        self.mysql_tray_menu.addAction(self.mysql_tray_access)

        self.redis_tray_menu = self.tray_menu.addMenu("Redis")
        redis_icon_path = os.path.join(BUNDLE_PATH, "redis.png")
        if os.path.exists(redis_icon_path):
            self.redis_tray_menu.setIcon(QIcon(redis_icon_path))
        self.redis_tray_run = QAction("", self)
        self.redis_tray_run.triggered.connect(lambda: self.toggle_service_action("redis", REDIS_PATH))
        self.redis_tray_access = QAction("", self)
        self.redis_tray_access.triggered.connect(lambda: self.toggle_access_action("redis"))
        self.redis_tray_menu.addAction(self.redis_tray_run)
        self.redis_tray_menu.addAction(self.redis_tray_access)

        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.exit_action)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

        # Dropdown bahasa
        self.lang_selector = QComboBox()
        for lang_code in get_languages():
            # Menampilkan nama (misal: Indonesia) tapi menyimpan kode (misal: id) sebagai data
            self.lang_selector.addItem(tr(lang_code, "lang_name"), lang_code)
        
        # Set posisi dropdown sesuai bahasa default
        index = self.lang_selector.findData(self.current_lang)
        if index >= 0: self.lang_selector.setCurrentIndex(index)
        
        self.lang_selector.currentIndexChanged.connect(self.change_language)

        # Checkboxes Settings
        self.chk_run_startup = QCheckBox()
        self.chk_run_startup.setChecked(get_setting('run_on_startup', '0') == '1')
        self.chk_run_startup.stateChanged.connect(self.toggle_startup)

        self.chk_auto_start_services = QCheckBox()
        self.chk_auto_start_services.setChecked(get_setting('auto_start_services', '0') == '1')
        self.chk_auto_start_services.stateChanged.connect(self.toggle_auto_start)

        # Tombol Buka Browser
        self.btn_open_browser = QPushButton()
        self.btn_open_browser.clicked.connect(lambda: webbrowser.open("http://localhost/"))

        # Tombol Port Settings
        self.btn_settings = QPushButton()
        self.btn_settings.clicked.connect(self.open_settings)

        # Tombol Scheduler Settings
        self.btn_scheduler_settings = QPushButton()
        self.btn_scheduler_settings.clicked.connect(self.open_scheduler)

        # Tombol Minimize to Tray
        self.btn_minimize = QPushButton()
        self.btn_minimize.clicked.connect(self.hide_to_tray)

        # Status labels
        self.apache_status = QLabel()
        self.mysql_status = QLabel()
        self.redis_status = QLabel()

        # Service Buttons (Access & Config)
        self.btn_apache_config = QPushButton()
        self.btn_apache_config.setMenu(self.apache_config_menu)
        self.btn_apache_www = QPushButton()
        self.btn_apache_www.clicked.connect(lambda: os.startfile(os.path.join(BASE_PATH, "www")))

        self.btn_mysql_config = QPushButton()
        self.btn_mysql_config.clicked.connect(lambda: self.open_config("mysql", True))
        self.btn_mysql_pma = QPushButton()
        self.btn_mysql_pma.clicked.connect(lambda: webbrowser.open(f"http://localhost:{get_setting('apache_port', '80')}/phpMyAdmin"))

        self.btn_mysql_password = QPushButton()
        self.btn_mysql_password.clicked.connect(self.open_mysql_password_dialog)

        self.btn_redis_config = QPushButton()
        self.btn_redis_config.clicked.connect(lambda: self.open_config("redis", True))
        self.btn_redis_cli = QPushButton()
        self.btn_redis_cli.clicked.connect(lambda: subprocess.Popen(
            [os.path.join(BASE_PATH, "redis", "redis-cli.exe")], 
            creationflags=subprocess.CREATE_NEW_CONSOLE
        ))

        # UI Logs
        self.log_label = QLabel()
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(3)
        self.btn_clear_logs = QPushButton()
        self.btn_clear_logs.clicked.connect(self.clear_logs)

        self.load_logs()

        log_signal.updated.connect(self.load_logs)

        # --- Layout setup (Grid) ---
        layout = QGridLayout()
        layout.setSpacing(10)

        # Baris 0: Bahasa & Browser
        layout.addWidget(self.lang_selector, 0, 0, 1, 1)
        layout.addWidget(self.btn_open_browser, 0, 1, 1, 1)
        layout.addWidget(self.btn_minimize, 0, 2, 1, 1)
        layout.addWidget(self.btn_scheduler_settings, 0, 3, 1, 1)
        layout.addWidget(self.btn_settings, 0, 4, 1, 1)
        layout.addWidget(self.btn_mysql_password, 0, 5)

        # Baris 1: Apache (Status, Run, Stop, Local, External)
        layout.addWidget(self.apache_status, 1, 0, 1, 2)
        layout.addWidget(self.btn_apache_toggle, 1, 2)
        layout.addWidget(self.btn_apache_access_toggle, 1, 3)
        layout.addWidget(self.btn_apache_config, 1, 4)
        layout.addWidget(self.btn_apache_www, 1, 5)

        # Baris 2: MySQL
        layout.addWidget(self.mysql_status, 2, 0, 1, 2)
        layout.addWidget(self.btn_mysql_toggle, 2, 2)
        layout.addWidget(self.btn_mysql_access_toggle, 2, 3)
        layout.addWidget(self.btn_mysql_config, 2, 4)
        layout.addWidget(self.btn_mysql_pma, 2, 5)
        
        # Baris 3: Redis
        layout.addWidget(self.redis_status, 3, 0, 1, 2)
        layout.addWidget(self.btn_redis_toggle, 3, 2)
        layout.addWidget(self.btn_redis_access_toggle, 3, 3)
        layout.addWidget(self.btn_redis_config, 3, 4)
        layout.addWidget(self.btn_redis_cli, 3, 5)

        # Baris 4 dan 5: Global Settings
        layout.addWidget(self.chk_run_startup, 4, 0, 1, 3)
        layout.addWidget(self.chk_auto_start_services, 5, 0, 1, 3)

        # Baris 6-7: Logs
        layout.addWidget(self.log_label, 6, 0, 1, 5)
        layout.addWidget(self.btn_clear_logs, 6, 5)
        layout.addWidget(self.log_table, 7, 0, 1, 6)

        self.setLayout(layout)

        # Simpan proses manual
        self.apache_proc = None
        self.mysql_proc = None
        self.redis_proc = None

        self.update_texts()

        # Timer to periodically update service status
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_service_status)
        self.status_timer.start(2000)

    def toggle_service_action(self, name, path):
        port_map = {
            "apache": int(get_setting('apache_port', '80')),
            "mysql": int(get_setting('mysql_port', '3306')),
            "redis": int(get_setting('redis_port', '6379'))
        }
        
        if is_port_in_use(port_map[name]):
            self.stop_service(name)
        else:
            self.run_service(name, path)
            
    def toggle_access_action(self, name):
        # Gunakan database sebagai referensi status, bukan pembacaan file fisik
        is_online = get_setting(f"{name}_access_mode", "local") == "external"
        self.change_access(name, not is_online)
            
    def open_config_file(self, config_path):
        try:
            if not os.path.exists(config_path):
                QMessageBox.warning(self, tr(self.current_lang, "fatal_error_title"), f"{tr(self.current_lang, 'msg_file_not_found')}\n{config_path}")
                return
            subprocess.Popen(["notepad.exe", config_path])
        except Exception as e:
            QMessageBox.critical(self, tr(self.current_lang, "fatal_error_title"), str(e))

    def open_config(self, service, use_notepad=True):
        try:
            # Mapping path config per service
            config_map = {
                "apache": os.path.join(BASE_PATH, "config", "httpd-template.conf"),
                "mysql": os.path.join(BASE_PATH, "config", "my-template.ini"),
                "redis": os.path.join(BASE_PATH, "config", "redis.windows-service-template.conf"),
                "php": os.path.join(BASE_PATH, "config", "php-template.ini"),
            }

            if service not in config_map:
                QMessageBox.warning(self, tr(self.current_lang, "fatal_error_title"), f"{tr(self.current_lang, 'msg_unknown_service')}\n{service}")
                return

            config_path = config_map[service]

            if not os.path.exists(config_path):
                QMessageBox.warning(self, tr(self.current_lang, "fatal_error_title"), f"{tr(self.current_lang, 'msg_file_not_found')}\n{config_path}")
                return

            # Buka dengan Notepad (default Windows)
            if use_notepad:
                subprocess.Popen(["notepad.exe", config_path])
            else:
                # fallback: buka dengan default app
                os.startfile(config_path)

        except Exception as e:
            QMessageBox.critical(self, tr(self.current_lang, "fatal_error_title"), str(e))

    def get_lang_dir(self, lang):
        if lang in config and 'lang_dir' in config[lang]:
            return config[lang]['lang_dir'].lower()
        return 'ltr'  # default

    def apply_layout_direction(self):
        direction = self.get_lang_dir(self.current_lang)
        if direction == 'rtl':
            self.setLayoutDirection(Qt.RightToLeft)
        else:
            self.setLayoutDirection(Qt.LeftToRight)

    def update_texts(self):
        lang = self.current_lang

        # Update teks tombol Apache (Toggle diupdate via update_service_status)
        self.btn_apache_config.setText(tr(lang, "btn_apache_config"))
        self.btn_apache_www.setText(tr(lang, "btn_open_www"))

        # Update teks tombol MariaDB
        self.btn_mysql_config.setText(tr(lang, "btn_mysql_config"))
        self.btn_mysql_pma.setText(tr(lang, "btn_phpmyadmin"))
        self.btn_mysql_password.setText(tr(lang, "btn_reset_mysql_password"))

        # Update teks tombol Redis
        self.btn_redis_config.setText(tr(lang, "btn_redis_config"))
        self.btn_redis_cli.setText(tr(lang, "btn_redis_cli"))

        self.btn_open_browser.setText(tr(lang, "btn_open_browser"))
        self.btn_minimize.setText(tr(lang, "btn_minimize"))
        self.btn_settings.setText(tr(lang, "btn_settings"))
        self.btn_scheduler_settings.setText(tr(lang, "btn_manage_scheduler"))

        self.show_action.setText(tr(self.current_lang, "tray_menu_show"))
        self.minimize_action.setText(tr(self.current_lang, "tray_menu_minimize"))
        self.exit_action.setText(tr(self.current_lang, "tray_menu_exit"))
        
        self.start_all_action.setText(tr(self.current_lang, "tray_start_all"))
        self.stop_all_action.setText(tr(self.current_lang, "tray_stop_all"))
        self.online_all_action.setText(tr(self.current_lang, "tray_online_all"))
        self.offline_all_action.setText(tr(self.current_lang, "tray_offline_all"))

        self.chk_run_startup.setText(tr(self.current_lang, "chk_run_startup"))
        self.chk_auto_start_services.setText(tr(self.current_lang, "chk_auto_start_services"))

        self.log_label.setText(tr(self.current_lang, "log_label"))
        self.btn_clear_logs.setText(tr(self.current_lang, "btn_clear_logs"))

        self.log_table.setHorizontalHeaderLabels([
            tr(self.current_lang, "col_log_time"),
            tr(self.current_lang, "col_log_level"),
            tr(self.current_lang, "col_log_msg")
        ])
        self.log_table.resizeColumnsToContents()

        self.update_service_status()
        self.apply_layout_direction()

    def change_language(self, index):
        code = self.lang_selector.itemData(index)
        if code:
            self.current_lang = code
            set_setting('language', code)
            self.update_texts()

    def change_access(self, name, external):
        if name == "apache": set_apache_access(external)
        elif name == "mysql": set_mysql_access(external)
        elif name == "redis": set_redis_access(external)
        self.update_service_status()

    def check_online_config(self, name):
        if name == "apache":
            conf_path = os.path.join(BASE_PATH, "config", "httpd.conf")
            search_str = "Listen 0.0.0.0"
        elif name == "mysql":
            conf_path = os.path.join(BASE_PATH, "config", "my.ini")
            search_str = "bind-address=0.0.0.0"
        elif name == "redis":
            conf_path = os.path.join(BASE_PATH, "redis", "redis.windows.conf")
            search_str = "bind 0.0.0.0"
        else:
            return False

        if os.path.exists(conf_path):
            try:
                with open(conf_path, "r", encoding='utf-8') as f:
                    content = f.read().replace(" ", "")
                    clean_search = search_str.replace(" ", "")
                    return clean_search in content
            except:
                pass
        return False

    def update_service_status(self):
        """Timer hanya memicu pembaruan UI untuk semua layanan secara kolektif."""
        for service in ["apache", "mysql", "redis"]:
            self.update_service_ui(service)

    def update_service_ui(self, name):
        """Fungsi mandiri untuk memperbarui seluruh elemen UI terkait satu layanan."""
        lang = self.current_lang
        
        # 1. Deteksi Port dan Mode
        port_defaults = {"apache": "80", "mysql": "3306", "redis": "6379"}
        port = int(get_setting(f"{name}_port", port_defaults[name]))
        is_running = is_port_in_use(port)
        is_online = get_setting(f"{name}_access_mode", "local") == "external"

        # 2. Update Tombol Start/Stop (Berbasis Aksi)
        run_key = f"btn_{name}_stop" if is_running else f"btn_{name}_run"
        run_text = tr(lang, run_key)
        getattr(self, f"btn_{name}_toggle").setText(run_text)
        
        tray_run = getattr(self, f"{name}_tray_run")
        tray_run.setText(run_text)
        run_icon = "stop.png" if is_running else "start.png"
        run_icon_path = os.path.join(BUNDLE_PATH, run_icon)
        if os.path.exists(run_icon_path):
            tray_run.setIcon(QIcon(run_icon_path))
        else:
            std_icon = QStyle.SP_MediaStop if is_running else QStyle.SP_MediaPlay
            tray_run.setIcon(self.style().standardIcon(std_icon))

        # 3. Update Tombol Mode Akses (Berbasis Status - Sesuai Permintaan)
        # Jika online, tampilkan "Public Mode". Jika offline, tampilkan "Local Mode".
        mode_key = f"btn_{name}_external" if is_online else f"btn_{name}_local"
        mode_text = tr(lang, mode_key)
        getattr(self, f"btn_{name}_access_toggle").setText(mode_text)
        
        tray_access = getattr(self, f"{name}_tray_access")
        tray_access.setText(mode_text)
        acc_icon = "public.png" if is_online else "local.png"
        acc_icon_path = os.path.join(BUNDLE_PATH, acc_icon)
        if os.path.exists(acc_icon_path):
            tray_access.setIcon(QIcon(acc_icon_path))
        else:
            std_icon = QStyle.SP_DriveNetIcon if is_online else QStyle.SP_DriveHDIcon
            tray_access.setIcon(self.style().standardIcon(std_icon))

        # 4. Update Label Status Utama (Berbasis Status)
        status_label = getattr(self, f"{name}_status")
        online_label = tr(lang, "status_public" if is_online else "status_local")
        
        if is_running:
            base_status = tr(lang, f"{name}_status_running")
            label_text = f"{base_status} ({online_label})"
            style = "color: green; font-weight: bold;"
        else:
            base_status = tr(lang, f"{name}_status")
            label_text = f"{base_status} ({online_label})"
            style = "color: red;"
        
        status_label.setText(label_text)
        status_label.setStyleSheet(style)

    def toggle_startup(self, state):
        enabled = (state == 2) # Qt.Checked
        set_setting('run_on_startup', '1' if enabled else '0')
        set_run_on_startup(enabled)

    def toggle_auto_start(self, state):
        enabled = (state == 2)
        set_setting('auto_start_services', '1' if enabled else '0')

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.restore_from_tray()

    def hide_to_tray(self):
        set_setting('start_minimized', '1')
        self.hide()

    def restore_from_tray(self):
        set_setting('start_minimized', '0')
        self.showNormal()
        self.activateWindow()

    def resizeEvent(self, event):
        if not self.isMinimized():
            self.resize_timer.start(500)  # Simpan 500ms setelah resize berhenti
        super().resizeEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            is_max = self.isMaximized()
            set_setting('window_maximized', '1' if is_max else '0')
        super().changeEvent(event)

    def save_window_size(self):
        if not self.isMinimized() and not self.isMaximized():
            set_setting('window_width', str(self.width()))
            set_setting('window_height', str(self.height()))

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec_()

    def open_scheduler(self):
        dialog = SchedulerDialog(self)
        dialog.exec_()

    def open_mysql_password_dialog(self):
        dialog = MariaDBPasswordDialog(self)
        dialog.exec_()

    def apply_port_settings(self):
        prepare_environment()
        # Re-apply current access modes with new ports
        set_apache_access(get_setting('apache_access_mode', 'local') == 'external', force=True)
        set_mysql_access(get_setting('mysql_access_mode', 'local') == 'external', force=True)
        set_redis_access(get_setting('redis_access_mode', 'local') == 'external', force=True)
        add_log("Settings updated and configurations regenerated.")

    def closeEvent(self, event):
        self.stop_all_services()
        QApplication.instance().quit()

    def start_all_services(self):
        for name in ["apache", "mysql", "redis"]:
            is_online = get_setting(f'{name}_access_mode', 'local') == 'external'
            # Re-apply config based on current DB setting
            if name == "apache": set_apache_access(is_online)
            elif name == "mysql": set_mysql_access(is_online)
            elif name == "redis": set_redis_access(is_online)
            
            path = APACHE_PATH if name == "apache" else (MYSQL_PATH if name == "mysql" else REDIS_PATH)
            self.run_service(name, path)

    def stop_all_services(self):
        for svc in ["apache", "mysql", "redis"]:
            self.stop_service(svc)

    def set_all_online(self):
        """Mengubah semua layanan ke Mode Publik (Online)."""
        add_log("Tray Action: Putting all services Online (Public Mode)...", "INFO")
        set_apache_access(True, force=True)
        set_mysql_access(True, force=True)
        set_redis_access(True, force=True)
        self.update_service_status()

    def set_all_offline(self):
        """Mengubah semua layanan ke Mode Lokal (Offline)."""
        add_log("Tray Action: Putting all services Offline (Local Mode)...", "INFO")
        set_apache_access(False, force=True)
        set_mysql_access(False, force=True)
        set_redis_access(False, force=True)
        self.update_service_status()

    def initialize_mariadb(self):
        add_log("Checking MariaDB data directory...")
        data_dir = os.path.join(BASE_PATH, "data", "mysql")
        system_db_dir = os.path.join(data_dir, "mysql")
        
        if not os.path.exists(system_db_dir):
            add_log("MariaDB system database not found. Starting installation...")
            install_bin = os.path.join(BASE_PATH, "mysql", "bin", "mariadb-install-db.exe")
            if not os.path.exists(install_bin):
                add_log("CRITICAL: mariadb-install-db.exe not found!", "ERROR")
                return False
            
            try:
                # Menjalankan proses inisialisasi secara sinkron (menunggu selesai)
                subprocess.run([install_bin, f"--datadir={data_dir}"], 
                               cwd=os.path.join(BASE_PATH, "mysql"),
                               creationflags=subprocess.CREATE_NO_WINDOW,
                               check=True)
                add_log("MariaDB installation completed successfully.")
                return True
            except Exception as e:
                add_log(f"MariaDB installation failed: {str(e)}", "ERROR")
                return False
        return True

    def run_service(self, name, path):
        service_root = os.path.dirname(os.path.dirname(path))
        
        # Port Check
        port_map = {
            "apache": int(get_setting('apache_port', '80')),
            "mysql": int(get_setting('mysql_port', '3306')),
            "redis": int(get_setting('redis_port', '6379'))
        }
        if name in port_map and is_port_in_use(port_map[name]):
            add_log(f"WARNING: Port {port_map[name]} already in use. {name} might fail to start.", "WARNING")

        if not os.path.exists(path):
            add_log(f"FAILED: Path not found - {path}", "ERROR")
            return

        if name == "mysql":
            if get_setting('mariadb_installed', '0') != '1':
                if not self.initialize_mariadb():
                    return

        try:
            args = [path]
            if name == "apache":
                conf = os.path.join(BASE_PATH, "config", "httpd.conf")
                args.extend(["-f", conf])
            elif name == "mysql":
                conf = os.path.join(BASE_PATH, "config", "my.ini")
                args.append(f"--defaults-file={conf}")
            elif name == "redis":
                conf = os.path.join(BASE_PATH, "redis", "redis.windows.conf")
                if os.path.exists(conf):
                    args.append(conf)

            add_log(f"Starting {name}: {' '.join(args)}")
            proc = subprocess.Popen(args, cwd=service_root, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if name == "apache": self.apache_proc = proc
            elif name == "mysql": 
                self.mysql_proc = proc
                set_setting('mariadb_installed', '1')
            elif name == "redis": self.redis_proc = proc
            
            set_setting(f"{name}_pid", str(proc.pid))
            add_log(f"SUCCESS: {name} started (PID: {proc.pid})")
        except Exception as e:
            add_log(f"FAILED to start {name}: {str(e)}", "ERROR")
        self.update_service_status()

    def stop_service(self, name):
        add_log(f"Stopping service: {name}")

        proc = getattr(self, f"{name}_proc")
        if proc and proc.poll() is None:
            try:
                # Graceful termination
                proc.terminate()
                proc.wait(timeout=5)
                add_log(f"Service {name} terminated gracefully.")
            except subprocess.TimeoutExpired:
                add_log(f"Service {name} didn't stop in time, forcing kill...", "WARNING")
                proc.kill()
        else:
            # Fallback menggunakan image name jika objek proses tidak tersedia (misal: aplikasi di-restart)
            # Menggunakan taskkill /IM /F sesuai permintaan pengguna.
            # PERHATIAN: Ini akan menghentikan SEMUA proses dengan nama gambar yang sama,
            # bukan hanya yang dimulai oleh panel ini.
            image_name_map = {
                "apache": "httpd.exe",
                "mysql": "mysqld.exe",
                "redis": "redis-server.exe"
            }
            image_name = image_name_map.get(name)
            if image_name:
                try:
                    subprocess.run(["taskkill", "/IM", image_name, "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW,
                                   check=True) # check=True akan memunculkan CalledProcessError untuk kode keluar non-nol
                    add_log(f"Sent forceful termination to all processes with image name {image_name}.")
                except subprocess.CalledProcessError:
                    add_log(f"No process with image name {image_name} found to terminate.", "INFO")
                except Exception as e:
                    add_log(f"Error while trying to terminate {image_name} by image name: {e}", "ERROR")
            else:
                add_log(f"Unknown service image name for {name}, cannot use taskkill /IM.", "ERROR")

        setattr(self, f"{name}_proc", None)
        set_setting(f"{name}_pid", "0")
        self.update_service_status()

    def load_logs(self):
        self.log_table.setRowCount(0)
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT timestamp, level, message FROM logs ORDER BY id DESC LIMIT 100")
            logs = cur.fetchall()
            conn.close()
            
        for row_data in logs:
            row_num = self.log_table.rowCount()
            self.log_table.insertRow(row_num)
            for i, data in enumerate(row_data):
                self.log_table.setItem(row_num, i, QTableWidgetItem(str(data)))
        self.log_table.resizeColumnsToContents()

    def clear_logs(self):
        with db_lock:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("DELETE FROM logs")
            conn.commit()
            conn.close()
        self.load_logs()

if __name__ == "__main__":
    try:
        # Fix agar ikon muncul di taskbar & title bar pada Windows
        if os.name == 'nt':
            myappid = 'kamshory.portableserver.panel.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

        app = QApplication(sys.argv)
        init_db()
        lang = get_setting('language', 'en')

        if os.name == 'nt':
            # Single instance check menggunakan Mutex
            # Simpan handle dalam variabel 'instance_mutex' agar tidak terhapus oleh garbage collector
            instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\PortableServerControlPanelMutex")
            if ctypes.windll.kernel32.GetLastError() == 183: # 183 = ERROR_ALREADY_EXISTS
                QMessageBox.information(None, tr(lang, "app_running_title"), tr(lang, "app_running_msg"))
                sys.exit(0)

        app.setQuitOnLastWindowClosed(False)
        # Menjalankan scheduler di thread terpisah
        threading.Thread(target=scheduler_loop, daemon=True).start()
        
        window = ControlPanel()
        if get_setting('auto_start_services', '0') == '1':
            window.start_all_services()
        if get_setting('start_minimized', '0') == '0':
            window.show()
            
        sys.exit(app.exec_())
    except Exception as e:
        # Jika error terjadi sebelum database siap, gunakan default 'en'
        try:
            lang = get_setting('language', 'en')
        except:
            lang = 'en'
            
        if 'app' not in locals():
            error_app = QApplication(sys.argv)
            
        # Jangan tampilkan pesan jika error terkait pembersihan folder temporary PyInstaller
        error_str = str(e)
        if "_MEI" in error_str and ("temporary directory" in error_str or "directory is not empty" in error_str.lower()):
            sys.exit(0)

        QMessageBox.critical(None, tr(lang, "fatal_error_title"), f"{tr(lang, 'fatal_error_msg')}\n{str(e)}")
        sys.exit(1)
