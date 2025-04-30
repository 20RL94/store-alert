import zipfile
import datetime

# Monkey-patch ZipInfo to avoid ValueError: timestamps before 1980
_orig_from_file = zipfile.ZipInfo.from_file

def safe_from_file(filename, arcname=None, *, strict_timestamps=True):
    zinfo = _orig_from_file(filename, arcname, strict_timestamps=False)
    if zinfo.date_time[0] < 1980:
        zinfo.date_time = (1980, 1, 1, 0, 0, 0)
    return zinfo

zipfile.ZipInfo.from_file = staticmethod(safe_from_file)

from setuptools import setup

APP = ['store-alert.py']  # Make sure your main script is named exactly 'main.py'
DATA_FILES = [
    'green_icon.png',
    'red_icon.png',
    'black_icon.png',
    'tabs_config.json'  # Include the config file if needed
]
OPTIONS = {
    'argv_emulation': True,
    'includes': ['PyQt5', 'plyer'],
    'packages': ['PyQt5', 'plyer'],
    'iconfile': None  # Replace with 'youricon.icns' if you have a Mac icon
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
