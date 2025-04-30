@echo off
echo === Upgrading pip ===
python -m pip install --upgrade pip

echo === Installing required packages ===
pip install PyQt6 PyQt6-WebEngine plyer

echo === Running store-alert.py ===
python store-alert.py

echo.
echo === Script has exited. Press any key to close. ===
pause >nul
