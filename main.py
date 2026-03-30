import sys, os, subprocess, threading, time, sqlite3, configparser, webbrowser, ctypes, socket
from PyQt5.QtCore import QTimer, QEvent, Qt, pyqtSignal, QObject
from datetime import datetime
from croniter import croniter
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QLabel,
                             QGridLayout, QLineEdit, QTableWidget, QTableWidgetItem, QCheckBox,
                             QComboBox, QMessageBox,
                             QSystemTrayIcon, QMenu, QAction, QStyle, QDialog)
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
    conn.commit()
    conn.close()

    prepare_environment()
    # Pastikan file konfigurasi sinkron dengan pengaturan database saat startup
    set_apache_access(get_setting('apache_access_mode', 'local') == 'external', force=True)
    set_mysql_access(get_setting('mysql_access_mode', 'local') == 'external', force=True)
    set_redis_access(get_setting('redis_access_mode', 'local') == 'external', force=True)

def add_log(message, level="INFO"):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)", (ts, level, message))
    conn.commit()
    conn.close()
    log_signal.updated.emit()

def get_setting(key, default='0'):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

# --- Scheduler thread ---
def scheduler_loop():
    while True:
        now = datetime.now()
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT cron_expr, command FROM jobs WHERE enabled=1")
        jobs = cur.fetchall()
        conn.close()

        for cron_expr, cmd in jobs:
            try:
                itr = croniter(cron_expr, now)
                prev_time = itr.get_prev(datetime)
                if abs((now - prev_time).total_seconds()) < 60:
                    subprocess.Popen(cmd, shell=True,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                pass
        time.sleep(30)

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
        
        self.btn_edit = QPushButton(tr(parent.current_lang, "btn_edit_job"))
        self.btn_edit.clicked.connect(self.edit_job)
        layout.addWidget(self.btn_edit, 5, 0)
        
        self.btn_delete = QPushButton(tr(parent.current_lang, "btn_delete_job"))
        self.btn_delete.clicked.connect(self.delete_job)
        layout.addWidget(self.btn_delete, 5, 1)

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
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id, cron_expr, command, enabled FROM jobs")
        for row_data in cur.fetchall():
            row_num = self.job_table.rowCount()
            self.job_table.insertRow(row_num)
            for i, data in enumerate(row_data):
                val = str(data)
                if i == 3: val = tr(self.parent.current_lang, "status_enabled") if data == 1 else tr(self.parent.current_lang, "status_disabled")
                self.job_table.setItem(row_num, i, QTableWidgetItem(val))
        conn.close()
        self.job_table.resizeColumnsToContents()

    def add_job(self):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT INTO jobs (cron_expr, command, enabled) VALUES (?, ?, ?)", 
                    (self.cron_input.text(), self.cmd_input.text(), 1 if self.chk_enabled.isChecked() else 0))
        conn.commit()
        conn.close()
        self.load_jobs()

    def edit_job(self):
        curr = self.job_table.currentRow()
        if curr >= 0:
            job_id = self.job_table.item(curr, 0).text()
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("UPDATE jobs SET cron_expr=?, command=?, enabled=? WHERE id=?", 
                        (self.cron_input.text(), self.cmd_input.text(), 1 if self.chk_enabled.isChecked() else 0, job_id))
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
        curr_pass = self.current_pass_input.text()
        new_pass = self.new_pass_input.text()
        repeat_pass = self.repeat_pass_input.text()
        force = self.chk_force_reset.isChecked()

        if new_pass != repeat_pass:
            QMessageBox.warning(self, "Error", tr(self.parent.current_lang, "msg_password_mismatch"))
            return

        if force:
            # Force Reset Logic
            self.parent.stop_service("mysql")
            time.sleep(1)
            
            init_file = os.path.join(BASE_PATH, "tmp", "reset_pass.sql")
            os.makedirs(os.path.dirname(init_file), exist_ok=True)
            sql_cmd = f"FLUSH PRIVILEGES;\nALTER USER 'root'@'localhost' IDENTIFIED BY '{new_pass}';\n"
            try:
                with open(init_file, "w") as f:
                    f.write(sql_cmd)
                
                conf = os.path.join(BASE_PATH, "config", "my.ini")
                args = [MYSQL_PATH, f"--defaults-file={conf}", f"--init-file={init_file}", "--console"]
                proc = subprocess.Popen(args, cwd=os.path.join(BASE_PATH, "mysql"), 
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                
                # Tunggu eksekusi file init
                time.sleep(5)
                subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, 
                               creationflags=subprocess.CREATE_NO_WINDOW)
                
                if os.path.exists(init_file):
                    os.remove(init_file)
                
                QMessageBox.information(self, "Success", tr(self.parent.current_lang, "msg_password_changed_success"))
                self.accept()
            except Exception as e:
                add_log(f"Force reset failed: {str(e)}", "ERROR")
                QMessageBox.critical(self, "Error", f"{tr(self.parent.current_lang, 'msg_password_change_failed')}\n{str(e)}")
        else:
            # Standard change using client
            client_path = os.path.join(BASE_PATH, "mysql", "bin", "mariadb.exe")
            if not os.path.exists(client_path):
                client_path = os.path.join(BASE_PATH, "mysql", "bin", "mysql.exe")
                
            if not os.path.exists(client_path):
                QMessageBox.critical(self, "Error", "MariaDB client (mariadb.exe/mysql.exe) not found.")
                return

            # Pastikan service menyala untuk ganti password normal
            if not is_port_in_use(int(get_setting('mysql_port', '3306'))):
                self.parent.run_service("mysql", MYSQL_PATH)
                time.sleep(2)

            sql = f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{new_pass}';"
            cmd = [client_path, "-u", "root"]
            if curr_pass:
                cmd.append(f"-p{curr_pass}")
            cmd.extend(["-e", sql])
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode == 0:
                    QMessageBox.information(self, "Success", tr(self.parent.current_lang, "msg_password_changed_success"))
                    self.accept()
                else:
                    err = result.stderr.lower()
                    if "access denied" in err:
                        QMessageBox.warning(self, "Error", tr(self.parent.current_lang, "msg_current_password_wrong"))
                    else:
                        QMessageBox.critical(self, "Error", f"{tr(self.parent.current_lang, 'msg_password_change_failed')}\n{result.stderr}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"{tr(self.parent.current_lang, 'msg_password_change_failed')}\n{str(e)}")

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
        online_icon = os.path.join(BUNDLE_PATH, "online.png")
        self.online_all_action.setIcon(QIcon(online_icon) if os.path.exists(online_icon) else self.style().standardIcon(QStyle.SP_DriveNetIcon))
        self.online_all_action.triggered.connect(self.set_all_online)

        self.offline_all_action = QAction("", self)
        offline_icon = os.path.join(BUNDLE_PATH, "offline.png")
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

        # Tombol Apache
        self.btn_apache_manual = QPushButton()
        self.btn_apache_manual.clicked.connect(lambda: self.run_service("apache", APACHE_PATH))
        self.btn_apache_stop = QPushButton()
        self.btn_apache_stop.clicked.connect(lambda: self.stop_service("apache"))
        self.btn_apache_local = QPushButton()
        self.btn_apache_local.clicked.connect(lambda: self.change_access("apache", False))
        self.btn_apache_external = QPushButton()
        self.btn_apache_external.clicked.connect(lambda: self.change_access("apache", True))

        # Tombol MariaDB
        self.btn_mysql_manual = QPushButton()
        self.btn_mysql_manual.clicked.connect(lambda: self.run_service("mysql", MYSQL_PATH))
        self.btn_mysql_stop = QPushButton()
        self.btn_mysql_stop.clicked.connect(lambda: self.stop_service("mysql"))
        self.btn_mysql_local = QPushButton()
        self.btn_mysql_local.clicked.connect(lambda: self.change_access("mysql", False))
        self.btn_mysql_external = QPushButton()
        self.btn_mysql_external.clicked.connect(lambda: self.change_access("mysql", True))
        # Tombol Password MariaDB
        self.btn_mysql_password = QPushButton()
        self.btn_mysql_password.clicked.connect(self.open_mysql_password_dialog)

        # Tombol Redis
        self.btn_redis_manual = QPushButton()
        self.btn_redis_manual.clicked.connect(lambda: self.run_service("redis", REDIS_PATH))
        self.btn_redis_stop = QPushButton()
        self.btn_redis_stop.clicked.connect(lambda: self.stop_service("redis"))
        self.btn_redis_local = QPushButton()
        self.btn_redis_local.clicked.connect(lambda: self.change_access("redis", False))
        self.btn_redis_external = QPushButton()
        self.btn_redis_external.clicked.connect(lambda: self.change_access("redis", True))

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
        layout.addWidget(self.btn_scheduler_settings, 0, 2, 1, 1)
        layout.addWidget(self.btn_settings, 0, 3, 1, 1)
        layout.addWidget(self.btn_minimize, 0, 4, 1, 1)

        # Baris 1: Apache (Status, Run, Stop, Local, External)
        layout.addWidget(self.apache_status, 1, 0)
        layout.addWidget(self.btn_apache_manual, 1, 1)
        layout.addWidget(self.btn_apache_stop, 1, 2)
        layout.addWidget(self.btn_apache_local, 1, 3)
        layout.addWidget(self.btn_apache_external, 1, 4)

        # Baris 2: MySQL
        layout.addWidget(self.mysql_status, 2, 0)
        layout.addWidget(self.btn_mysql_manual, 2, 1)
        layout.addWidget(self.btn_mysql_stop, 2, 2)
        layout.addWidget(self.btn_mysql_local, 2, 3)
        layout.addWidget(self.btn_mysql_external, 2, 4)
        layout.addWidget(self.btn_mysql_password, 2, 5)

        # Baris 3: Redis
        layout.addWidget(self.redis_status, 3, 0)
        layout.addWidget(self.btn_redis_manual, 3, 1)
        layout.addWidget(self.btn_redis_stop, 3, 2)
        layout.addWidget(self.btn_redis_local, 3, 3)
        layout.addWidget(self.btn_redis_external, 3, 4)

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
        self.btn_apache_manual.setText(tr(self.current_lang, "btn_apache_run"))
        self.btn_apache_stop.setText(tr(self.current_lang, "btn_apache_stop"))
        self.btn_apache_local.setText(tr(self.current_lang, "btn_apache_local"))
        self.btn_apache_external.setText(tr(self.current_lang, "btn_apache_external"))

        self.btn_mysql_manual.setText(tr(self.current_lang, "btn_mysql_run"))
        self.btn_mysql_stop.setText(tr(self.current_lang, "btn_mysql_stop"))
        self.btn_mysql_local.setText(tr(self.current_lang, "btn_mysql_local"))
        self.btn_mysql_external.setText(tr(self.current_lang, "btn_mysql_external"))
        self.btn_mysql_password.setText(tr(self.current_lang, "btn_reset_mysql_password"))

        self.btn_redis_manual.setText(tr(self.current_lang, "btn_redis_run"))
        self.btn_redis_stop.setText(tr(self.current_lang, "btn_redis_stop"))
        self.btn_redis_local.setText(tr(self.current_lang, "btn_redis_local"))
        self.btn_redis_external.setText(tr(self.current_lang, "btn_redis_external"))

        self.btn_open_browser.setText(tr(self.current_lang, "btn_open_browser"))
        self.btn_minimize.setText(tr(self.current_lang, "btn_minimize"))
        self.btn_settings.setText(tr(self.current_lang, "btn_settings"))
        self.btn_scheduler_settings.setText(tr(self.current_lang, "btn_manage_scheduler"))

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
        online_str = tr(self.current_lang, "status_online")
        offline_str = tr(self.current_lang, "status_offline")

        def get_status_info(name, port):
            is_running = is_port_in_use(port)
            is_online = self.check_online_config(name)
            if is_running:
                base_text = tr(self.current_lang, f"{name}_status_running")
                mode = online_str if is_online else offline_str
                return f"{base_text} ({mode})", "color: green; font-weight: bold;"
            else:
                return tr(self.current_lang, f"{name}_status"), "color: red;"

        # Apache
        port_apache = int(get_setting('apache_port', '80'))
        text, style = get_status_info("apache", port_apache)
        self.apache_status.setText(text)
        self.apache_status.setStyleSheet(style)

        # MySQL
        port_mysql = int(get_setting('mysql_port', '3306'))
        text, style = get_status_info("mysql", port_mysql)
        self.mysql_status.setText(text)
        self.mysql_status.setStyleSheet(style)

        # Redis
        port_redis = int(get_setting('redis_port', '6379'))
        text, style = get_status_info("redis", port_redis)
        self.redis_status.setText(text)
        self.redis_status.setStyleSheet(style)

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
        # Apache
        apache_mode = get_setting('apache_access_mode', 'local') == 'external'
        set_apache_access(apache_mode)
        self.run_service("apache", APACHE_PATH)

        # MySQL
        mysql_mode = get_setting('mysql_access_mode', 'local') == 'external'
        set_mysql_access(mysql_mode)
        self.run_service("mysql", MYSQL_PATH)

        # Redis
        redis_mode = get_setting('redis_access_mode', 'local') == 'external'
        set_redis_access(redis_mode)
        self.run_service("redis", REDIS_PATH)

    def stop_all_services(self):
        for svc in ["apache", "mysql", "redis"]:
            self.stop_service(svc)

    def set_all_online(self):
        set_apache_access(True)
        set_mysql_access(True)
        set_redis_access(True)
        self.update_service_status()

    def set_all_offline(self):
        set_apache_access(False)
        set_mysql_access(False)
        set_redis_access(False)
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
            add_log(f"SUCCESS: {name} started (PID: {proc.pid})")
        except Exception as e:
            add_log(f"FAILED to start {name}: {str(e)}", "ERROR")
        self.update_service_status()

    def stop_service(self, name):
        add_log(f"Stopping service: {name}")
        
        # Mapping nama layanan ke nama file eksekutabel sesuai stop.php
        exe_map = {
            "apache": "httpd.exe",
            "mysql": "mysqld.exe",
            "redis": "redis-server.exe"
        }
        
        exe_name = exe_map.get(name)
        if exe_name:
            # Menggunakan taskkill /F /IM untuk menghentikan proses secara paksa
            # seperti pada logika stop.php
            subprocess.run(["taskkill", "/F", "/IM", exe_name], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            add_log(f"Command sent to stop {exe_name}")

        setattr(self, f"{name}_proc", None)
        self.update_service_status()

    def load_logs(self):
        self.log_table.setRowCount(0)
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # Tampilkan log terbaru di paling atas
        cur.execute("SELECT timestamp, level, message FROM logs ORDER BY id DESC LIMIT 100")
        for row_data in cur.fetchall():
            row_num = self.log_table.rowCount()
            self.log_table.insertRow(row_num)
            for i, data in enumerate(row_data):
                self.log_table.setItem(row_num, i, QTableWidgetItem(str(data)))
        conn.close()
        self.log_table.resizeColumnsToContents()

    def clear_logs(self):
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
