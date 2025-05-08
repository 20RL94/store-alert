@echo off
set "MAIN=store_alert.py"
set "NAME=WebMonitor"

echo Building %NAME%...

pyinstaller ^
  --onefile ^
  --name "%NAME%" ^
  --add-data "tabs_config.json;." ^
  --add-data "alert.mp3;." ^
  --add-data "clickable_label.py;." ^
  --add-data "patches.py;." ^
  %MAIN%

echo Copying patch and config to dist...
copy /Y patches.py dist\
copy /Y tabs_config.json dist\
copy /Y alert.mp3 dist\
copy /Y clickable_label.py dist\

echo Done.
pause
