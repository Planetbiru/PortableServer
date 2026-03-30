# Portable Server Control Panel

A lightweight, portable server management tool built with Python and PyQt5. This application allows you to manage Apache, MariaDB (MySQL), and Redis services with ease, featuring a built-in cron scheduler and activity logging.

## Advantages

Portable Server Control Panel has several key advantages that distinguish it from many other server panels, especially those that are web-based or require complex installations:

### Maximum Portability (True Portable)

**No Installation/Registry:**
This application is designed to be truly portable. Simply extract the folder to any location (USB drive, cloud folder, etc.) and run it. There are no traces left on the operating system (such as registry entries or files in Program Files), unless the "Run on Windows Startup" feature is manually enabled. This is ideal for developers, educators, or anyone who needs a quick server environment across multiple machines.

**Isolated Environment:**
All dependencies, configurations, and service data (Apache, MariaDB, Redis) are stored within a single directory. This minimizes conflicts with other server installations on the system and makes backup or migration easier.

### Flexible Local and Public Control

**Easy Mode Switching:**
The panel allows you to quickly switch between "Local Mode" (accessible only from the local machine, 127.0.0.1) and "Public Mode" (accessible from the network, 0.0.0.0). This is a very useful feature for both security and convenience during local development or presentations, without needing to manually edit configuration files.

**Automatic Port Detection:**
Before running services, the application checks whether required ports (such as 80 or 3306) are already in use, providing warnings to avoid conflicts.

### Enhanced Security and Stability

**Secure MariaDB "Force Reset" Feature:**
If the MariaDB root password is forgotten, the force reset feature can be used. Importantly, this feature is protected by a separate Administrator Password that is hashed (using SHA-256) and stored in an internal database. This prevents unauthorized users from resetting the database password.

**Graceful Process Management:**
Services (Apache, MariaDB, Redis) are stopped gracefully, allowing them time to close connections and save data instead of being forcefully terminated. This reduces the risk of data corruption and improves system stability. The application also tracks running service PIDs.

**Mutex for Single Instance:**
Ensures that only one instance of the application runs at a time, preventing conflicts and unnecessary resource usage.

### Powerful Automation and Task Management

**Built-in Cron Scheduler:**
The panel includes a powerful cron scheduler that allows you to run system commands or PHP/Python scripts automatically at specified intervals. This is highly useful for maintenance tasks, backups, or running background scripts.

**Background Task Management:**
Tasks executed by the scheduler run in the background without intrusive console windows, making it ideal for automation.

### Intuitive and Multilingual User Experience

**Responsive PyQt5 Interface:**
The UI built with PyQt5 provides a fast and responsive desktop experience.

**Comprehensive System Tray Integration:**
The application can run in the background, with all essential controls (start/stop/access mode) available through the system tray icon, including dynamic icons for each service that display their status.

**Full Multilingual Support (Including RTL):**
The application supports multiple languages with consistent translations and even automatic layout adjustments for Right-to-Left (RTL) languages such as Arabic and Urdu, ensuring broad accessibility.

**Real-time Activity Logging:**
All important actions and service statuses are logged in real-time into a SQLite database, making monitoring and debugging easier.

### Automatic and Flexible Configuration

**Template-based Configuration Generation:**
The application automatically generates configuration files for Apache, MariaDB, and Redis from templates, dynamically injecting installation paths and port settings. This simplifies customization and maintenance.

---

In summary, Portable Server Control Panel stands out for its focus on portability, ease of use, security, and advanced automation capabilities—features that are rarely found together in other server panels. This makes it a highly valuable tool for developers and administrators seeking an efficient and reliable local server solution.

## 🚀 Features

*   **Service Management:** Individual and batch control (Start/Stop) for Apache, MariaDB, and Redis.
*   **Access Control:** Quickly toggle services between **Local Mode** (127.0.0.1) and **Public Mode** (0.0.0.0).
*   **MariaDB Password Management:** Change or reset the MariaDB root password. Features a secure **Force Reset** protected by a hashed Administrator Password.
*   **Precise Cron Scheduler:** Execute system commands or PHP scripts using cron expressions. Tasks run in the background without console windows. Status can be toggled directly from the UI.
*   **System Tray Integration:** Run in the background with dynamic tray icons. Control individual services via submenus featuring Start, Stop, Public, and Local status icons.
*   **Port Collision Detection:** Automatically checks if ports 80 (Apache) or 3306 (MySQL) are already in use before starting services.
*   **Activity Logging:** Real-time logging of service actions, PID tracking, and environment changes, stored in a thread-safe SQLite database.
*   **Automatic Configuration:** Automatically generates configuration files (`httpd.conf`, `php.ini`, `my.ini`, `redis.conf`) from templates, dynamically injecting the current installation directory path.
*   **Multi-language Support:** Comprehensive localization including English, Indonesian, Malay, Javanese, Sundanese, Chinese, Japanese, Korean, Hindi, Arabic, and Urdu.
*   **RTL Support:** Automatic layout adjustment for Right-to-Left languages like Arabic and Urdu.
*   **Windows Integration:** Graceful process termination, option to run on Windows startup, and built-in Mutex to prevent multiple instances.
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
4.  Add cron jobs in the scheduler section to automate tasks. You can enable/disable jobs by update it status in the database.

## 📂 Project Structure

### Core Files
*   **`main.py`**: The central engine of the application. It manages the PyQt5 GUI, handles SQLite database operations (logs and settings), orchestrates the cron scheduler, and controls the lifecycle of Apache, MariaDB, and Redis processes.
*   **`localization.ini`**: A comprehensive configuration file containing all UI strings. It enables multi-language support and defines layout directions (LTR/RTL) for various locales.
*   **`icon.ico`**: The primary application icon used for the main window, taskbar, and executable branding.

### System Tray & UI Assets
These images provide visual feedback and intuitive controls within the system tray menu:
*   **Service Branding** (`apache.png`, `mariadb.png`, `redis.png`): Used as icons for service-specific submenus in the tray.
*   **Status Indicators**:
    *   `start.png` / `stop.png`: Dynamically updated icons representing whether a service is active or inactive.
    *   `public.png` / `local.png`: Visual cues for Public (0.0.0.0) vs. Local (127.0.0.1) access modes.
*   **Window & App Control**:
    *   `maximize.png` / `minimize.png`: Represent the "Show" and "Minimize to Tray" actions.
    *   `exit.png`: The icon for the "Exit" action to terminate the panel and its managed services.


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
  --add-data "public.png;." ^
  --add-data "local.png;." ^
  --add-data "apache.png;." ^
  --add-data "mariadb.png;." ^
  --add-data "redis.png;." ^
  --add-data "exit.png;." ^
  --exclude-module numpy --exclude-module pandas --exclude-module matplotlib ^
  main.py
```

## 📄 License

This project is open-source and available under the MIT License.

---
*Created by Kamshory*

*Note: This project was designed to be portable. Ensure you have the necessary permissions to write to the application directory.*
