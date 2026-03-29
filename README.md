# Portable Server Control Panel

A lightweight, portable server management tool built with Python and PyQt5. This application allows you to manage Apache, MariaDB (MySQL), and Redis services with ease, featuring a built-in cron scheduler and activity logging.

## 🚀 Features

*   **Service Management:** Individual and batch control (Start/Stop) for Apache, MariaDB, and Redis.
*   **Access Control:** Quickly toggle services between **Local Mode** (127.0.0.1) and **Public Mode** (0.0.0.0).
*   **Cron Scheduler:** Manage scheduled tasks using standard cron expressions to execute system commands.
*   **System Tray Integration:** Run the application in the background. Minimize to tray and control services via the context menu.
*   **Port Collision Detection:** Automatically checks if ports 80 (Apache) or 3306 (MySQL) are already in use before starting services.
*   **Activity Logging:** Real-time logging of service actions and environment changes, stored in a local SQLite database.
*   **Automatic Configuration:** Automatically generates configuration files (`httpd.conf`, `php.ini`, `my.ini`, `redis.conf`) from templates, dynamically injecting the current installation directory path.
*   **Multi-language Support:** Comprehensive localization including English, Indonesian, Malay, Javanese, Sundanese, Chinese, Japanese, Korean, Hindi, and Arabic (with RTL support).
*   **Windows Integration:** Option to run on Windows startup and built-in Mutex to prevent multiple instances from running.
*   **Responsive UI:** Remembers your window size and maximization state for the next session.

## 🛠️ Prerequisites

*   **Operating System:** Windows (uses Windows-specific APIs for Mutex, Registry, and Process management).
*   **Python:** 3.10 or higher recommended.
*   **Server Binaries:** The application expects the following directory structure in the root folder:
    *   `/apache` (containing `bin/httpd.exe`)
    *   `/mysql` (containing `bin/mysqld.exe`)
    *   `/redis` (containing `redis-server.exe`)
    *   `/php` (containing `php.exe` and extensions)

## 📦 Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Planetbiru/PortableServer.git
    cd PortableServer
    ```

2.  **Install dependencies:**
    ```bash
    pip install PyQt5 croniter
    ```

3.  **Setup Templates:** Ensure your `config/` folder contains the template files (e.g., `httpd-template.conf`). Use `${INSTALL_DIR}` or `{ROOT}` placeholders in these files for dynamic path replacement.

## 🖥️ Usage

1.  Run the application:
    ```bash
    python main.py
    ```
2.  The application will automatically prepare the environment (create `www`, `logs`, `tmp` folders) and generate configuration files.
3.  Use the main panel to start your services.
4.  Add cron jobs in the scheduler section to automate tasks.

## 📂 Project Structure

*   `main.py`: The entry point and main logic of the application.
*   `localization.ini`: Translation strings for multi-language support.
*   `scheduler.db`: SQLite database for settings, jobs, and logs.
*   `config/`: Folder containing configuration templates.
*   `icon-maker.html`: A handy tool to generate project icons from SVG paths.

## 🛠️ Building the Executable

To bundle the application into a single `.exe` file using PyInstaller:

```bash
python -m PyInstaller ^
  --noconsole ^
  --onefile ^
  --name PortableServer ^
  --icon=icon.ico ^
  --hidden-import=croniter ^
  --hidden-import=dateutil ^
  --add-data "icon.ico;." ^
  --add-data "maximize.png;." ^
  --add-data "minimize.png;." ^
  --add-data "start.png;." ^
  --add-data "stop.png;." ^
  --add-data "online.png;." ^
  --add-data "offline.png;." ^
  --add-data "exit.png;." ^
  --exclude-module numpy --exclude-module pandas --exclude-module matplotlib ^
  main.py
```

## 📄 License

This project is open-source and available under the MIT License.

---
*Created by Kamshory*

*Note: This project was designed to be portable. Ensure you have the necessary permissions to write to the application directory.*
