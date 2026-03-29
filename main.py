import sys, os, subprocess, threading, time, sqlite3, configparser, webbrowser, ctypes
from datetime import datetime
from croniter import croniter
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QLabel,
                             QGridLayout, QLineEdit, QTableWidget, QTableWidgetItem,
                             QHBoxLayout, QComboBox, QVBoxLayout, QMessageBox)
from PyQt5.QtGui import QIcon

if getattr(sys, 'frozen', False):
    # Lokasi folder tempat file .exe berada (untuk DB, INI, dan folder server)
    BASE_PATH = os.path.dirname(sys.executable)
    # Path internal bundle khusus untuk resource yang di-embed (seperti icon)
    BUNDLE_PATH = getattr(sys, '_MEIPASS', BASE_PATH)
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_PATH = BASE_PATH

DB_PATH = os.path.join(BASE_PATH, "scheduler.db")
INI_PATH = os.path.join(BASE_PATH, "localization.ini")

APACHE_PATH = os.path.join(BASE_PATH, "apache", "bin", "httpd.exe")
MYSQL_PATH = os.path.join(BASE_PATH, "mysql", "bin", "mysqld.exe")
REDIS_PATH = os.path.join(BASE_PATH, "redis", "redis-server.exe")

# --- Localization ---
config = configparser.ConfigParser()
config.read(INI_PATH)

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
        command TEXT NOT NULL
    )""")
    conn.commit()
    conn.close()

# --- Scheduler thread ---
def scheduler_loop():
    while True:
        now = datetime.now()
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT cron_expr, command FROM jobs")
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
def set_apache_access(external=False):
    conf_path = os.path.join(BASE_PATH, "apache", "conf", "httpd.conf")
    if os.path.exists(conf_path):
        with open(conf_path, "r") as f:
            lines = f.readlines()
        with open(conf_path, "w") as f:
            for line in lines:
                if line.strip().startswith("Listen"):
                    f.write("Listen 0.0.0.0:80\n" if external else "Listen 127.0.0.1:80\n")
                else:
                    f.write(line)

def set_mysql_access(external=False):
    conf_path = os.path.join(BASE_PATH, "mysql", "my.ini")
    if os.path.exists(conf_path):
        with open(conf_path, "r") as f:
            lines = f.readlines()
        with open(conf_path, "w") as f:
            for line in lines:
                if line.strip().startswith("bind-address"):
                    f.write("bind-address=0.0.0.0\n" if external else "bind-address=127.0.0.1\n")
                else:
                    f.write(line)

def set_redis_access(external=False):
    conf_path = os.path.join(BASE_PATH, "redis", "redis.conf")
    if os.path.exists(conf_path):
        with open(conf_path, "r") as f:
            lines = f.readlines()
        with open(conf_path, "w") as f:
            for line in lines:
                if line.strip().startswith("bind"):
                    f.write("bind 0.0.0.0\n" if external else "bind 127.0.0.1\n")
                else:
                    f.write(line)

class ControlPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Server Control Panel")
        self.setGeometry(300, 300, 700, 600)

        # Tambahkan padding horizontal agar caption tidak menyentuh tepi tombol
        self.setStyleSheet("""
            QPushButton {
                padding-left: 15px;
                padding-right: 15px;
                min-height: 25px;
            }
        """)

        # Set Window Icon
        icon_path = os.path.join(BUNDLE_PATH, "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.current_lang = "en"

        # Dropdown bahasa
        self.lang_selector = QComboBox()
        for lang_code in get_languages():
            # Menampilkan nama (misal: Indonesia) tapi menyimpan kode (misal: id) sebagai data
            self.lang_selector.addItem(tr(lang_code, "lang_name"), lang_code)
        
        # Set posisi dropdown sesuai bahasa default
        index = self.lang_selector.findData(self.current_lang)
        if index >= 0: self.lang_selector.setCurrentIndex(index)
        
        self.lang_selector.currentIndexChanged.connect(self.change_language)

        # Tombol Buka Browser
        self.btn_open_browser = QPushButton()
        self.btn_open_browser.clicked.connect(lambda: webbrowser.open("http://localhost/"))

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
        self.btn_apache_local.clicked.connect(lambda: set_apache_access(False))
        self.btn_apache_external = QPushButton()
        self.btn_apache_external.clicked.connect(lambda: set_apache_access(True))

        # Tombol MariaDB
        self.btn_mysql_manual = QPushButton()
        self.btn_mysql_manual.clicked.connect(lambda: self.run_service("mysql", MYSQL_PATH))
        self.btn_mysql_stop = QPushButton()
        self.btn_mysql_stop.clicked.connect(lambda: self.stop_service("mysql"))
        self.btn_mysql_local = QPushButton()
        self.btn_mysql_local.clicked.connect(lambda: set_mysql_access(False))
        self.btn_mysql_external = QPushButton()
        self.btn_mysql_external.clicked.connect(lambda: set_mysql_access(True))

        # Tombol Redis
        self.btn_redis_manual = QPushButton()
        self.btn_redis_manual.clicked.connect(lambda: self.run_service("redis", REDIS_PATH))
        self.btn_redis_stop = QPushButton()
        self.btn_redis_stop.clicked.connect(lambda: self.stop_service("redis"))
        self.btn_redis_local = QPushButton()
        self.btn_redis_local.clicked.connect(lambda: set_redis_access(False))
        self.btn_redis_external = QPushButton()
        self.btn_redis_external.clicked.connect(lambda: set_redis_access(True))

        # Scheduler UI
        self.scheduler_label = QLabel()
        self.cron_input = QLineEdit("*/1 * * * *")
        self.cmd_input = QLineEdit("echo Hello World")
        self.btn_add_job = QPushButton()
        self.btn_add_job.clicked.connect(self.add_job)

        # Tabel job
        self.job_table = QTableWidget()
        self.job_table.setColumnCount(3)
        self.load_jobs()

        # Tombol edit/hapus
        self.btn_edit_job = QPushButton()
        self.btn_edit_job.clicked.connect(self.edit_job)
        self.btn_delete_job = QPushButton()
        self.btn_delete_job.clicked.connect(self.delete_job)

        # --- Layout setup (Grid) ---
        layout = QGridLayout()
        layout.setSpacing(10)

        # Baris 0: Bahasa & Browser
        layout.addWidget(self.lang_selector, 0, 0, 1, 3)
        layout.addWidget(self.btn_open_browser, 0, 3, 1, 2)

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

        # Baris 3: Redis
        layout.addWidget(self.redis_status, 3, 0)
        layout.addWidget(self.btn_redis_manual, 3, 1)
        layout.addWidget(self.btn_redis_stop, 3, 2)
        layout.addWidget(self.btn_redis_local, 3, 3)
        layout.addWidget(self.btn_redis_external, 3, 4)

        # Baris 4: Scheduler Label
        layout.addWidget(self.scheduler_label, 4, 0, 1, 5)

        # Baris 5: Scheduler Inputs
        layout.addWidget(self.cron_input, 5, 0, 1, 1)
        layout.addWidget(self.cmd_input, 5, 1, 1, 3)
        layout.addWidget(self.btn_add_job, 5, 4)

        # Baris 6: Table (Span 5 columns)
        layout.addWidget(self.job_table, 6, 0, 1, 5)

        # Baris 7: Table Actions
        layout.addWidget(self.btn_edit_job, 7, 0, 1, 3)
        layout.addWidget(self.btn_delete_job, 7, 3, 1, 2)

        self.setLayout(layout)

        # Simpan proses manual
        self.apache_proc = None
        self.mysql_proc = None
        self.redis_proc = None

        self.update_texts()

    def update_texts(self):
        self.apache_status.setText(tr(self.current_lang, "apache_status"))
        self.btn_apache_manual.setText(tr(self.current_lang, "btn_apache_run"))
        self.btn_apache_stop.setText(tr(self.current_lang, "btn_apache_stop"))
        self.btn_apache_local.setText(tr(self.current_lang, "btn_apache_local"))
        self.btn_apache_external.setText(tr(self.current_lang, "btn_apache_external"))

        self.mysql_status.setText(tr(self.current_lang, "mysql_status"))
        self.btn_mysql_manual.setText(tr(self.current_lang, "btn_mysql_run"))
        self.btn_mysql_stop.setText(tr(self.current_lang, "btn_mysql_stop"))
        self.btn_mysql_local.setText(tr(self.current_lang, "btn_mysql_local"))
        self.btn_mysql_external.setText(tr(self.current_lang, "btn_mysql_external"))

        self.redis_status.setText(tr(self.current_lang, "redis_status"))
        self.btn_redis_manual.setText(tr(self.current_lang, "btn_redis_run"))
        self.btn_redis_stop.setText(tr(self.current_lang, "btn_redis_stop"))
        self.btn_redis_local.setText(tr(self.current_lang, "btn_redis_local"))
        self.btn_redis_external.setText(tr(self.current_lang, "btn_redis_external"))

        self.scheduler_label.setText(tr(self.current_lang, "scheduler_label"))
        self.btn_add_job.setText(tr(self.current_lang, "btn_add_job"))
        self.btn_edit_job.setText(tr(self.current_lang, "btn_edit_job"))
        self.btn_delete_job.setText(tr(self.current_lang, "btn_delete_job"))
        self.btn_open_browser.setText(tr(self.current_lang, "btn_open_browser"))

        # Update tabel header sesuai bahasa
        self.job_table.setHorizontalHeaderLabels([
            tr(self.current_lang, "col_id"),
            tr(self.current_lang, "col_cron"),
            tr(self.current_lang, "col_cmd")
        ])

    def change_language(self, index):
        code = self.lang_selector.itemData(index)
        if code:
            self.current_lang = code
            self.update_texts()

    def run_service(self, name, path):
        if not os.path.exists(path): return
        proc = subprocess.Popen([path], creationflags=subprocess.CREATE_NO_WINDOW)
        if name == "apache": self.apache_proc = proc
        elif name == "mysql": self.mysql_proc = proc
        elif name == "redis": self.redis_proc = proc

    def stop_service(self, name):
        proc = getattr(self, f"{name}_proc", None)
        if proc:
            proc.terminate()
            setattr(self, f"{name}_proc", None)

    def load_jobs(self):
        self.job_table.setRowCount(0)
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT * FROM jobs")
        for row_data in cur.fetchall():
            row_num = self.job_table.rowCount()
            self.job_table.insertRow(row_num)
            for i, data in enumerate(row_data):
                self.job_table.setItem(row_num, i, QTableWidgetItem(str(data)))
        conn.close()

    def add_job(self):
        cron, cmd = self.cron_input.text(), self.cmd_input.text()
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT INTO jobs (cron_expr, command) VALUES (?, ?)", (cron, cmd))
        conn.commit()
        conn.close()
        self.load_jobs()

    def edit_job(self):
        curr = self.job_table.currentRow()
        if curr >= 0:
            job_id = self.job_table.item(curr, 0).text()
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("UPDATE jobs SET cron_expr=?, command=? WHERE id=?", 
                        (self.cron_input.text(), self.cmd_input.text(), job_id))
            conn.commit()
            conn.close()
            self.load_jobs()

    def delete_job(self):
        curr = self.job_table.currentRow()
        if curr >= 0:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Question)
            msg.setWindowTitle(tr(self.current_lang, "confirm_delete_title"))
            msg.setText(tr(self.current_lang, "confirm_delete_msg"))
            
            btn_yes = msg.addButton(tr(self.current_lang, "btn_yes"), QMessageBox.YesRole)
            btn_no = msg.addButton(tr(self.current_lang, "btn_no"), QMessageBox.NoRole)
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

if __name__ == "__main__":
    try:
        # Fix agar ikon muncul di taskbar & title bar pada Windows
        if os.name == 'nt':
            myappid = 'kamshory.portableserver.panel.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            
        app = QApplication(sys.argv)
        init_db()
        # Menjalankan scheduler di thread terpisah
        threading.Thread(target=scheduler_loop, daemon=True).start()
        
        window = ControlPanel()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        error_app = QApplication(sys.argv)
        QMessageBox.critical(None, "Fatal Error", f"Aplikasi gagal dimulai:\n{str(e)}")
        sys.exit(1)
