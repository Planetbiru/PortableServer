
```bash
pip install pyinstaller croniter PyQt5


python -m PyInstaller --noconsole --onedir --name PortableServer --icon=icon.ico --add-data "icon.ico;." main.py

or

python -m PyInstaller --noconsole --onedir --name PortableServer --icon=icon.ico --hidden-import=croniter --hidden-import=dateutil main.py

```
