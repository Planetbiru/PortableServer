
```bash
pip install pyinstaller croniter PyQt5

python -m PyInstaller --noconsole --onefile --name PortableServer --icon=icon.ico --add-data "icon.ico;." main.py

or

python -m PyInstaller --noconsole --onefile --name PortableServer --icon=icon.ico --add-data "icon.ico;." --add-data "scheduler.db;." main.py

python -m PyInstaller --noconsole --onefile --name PortableServer --icon=icon.ico --hidden-import=croniter --hidden-import=dateutil main.py
```

```bash
python -m PyInstaller ^
  --noconsole ^
  --onefile ^
  --name PortableServer ^
  --icon=icon.ico ^
  --hidden-import=croniter ^
  --hidden-import=dateutil ^
  --add-data "icon.ico;." ^
  --add-data "show.png;." ^
  --add-data "start.png;." ^
  --add-data "stop.png;." ^
  --add-data "online.png;." ^
  --add-data "offline.png;." ^
  --add-data "exit.png;." ^
  --exclude-module numpy --exclude-module pandas --exclude-module matplotlib ^
  main.py

```