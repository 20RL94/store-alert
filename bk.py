# Full updated code with global threshold and delay dropdowns in the top-right control pane.

import sys
import json
import os
import platform
from datetime import datetime
from PyQt5.QtCore import QUrl, QTimer, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QLineEdit, QPushButton, QHBoxLayout, QInputDialog, QMenu, QComboBox, QLabel
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from plyer import notification
import logging

# Suppress Wayland warning
os.environ["QT_QPA_PLATFORM"] = "wayland"
logging.basicConfig(level=logging.ERROR)

if platform.system() == "Windows":
    import winsound
else:
    import subprocess

CONFIG_FILE = "tabs_config.json"


class MonitorTab(QWidget):
    def __init__(self, parent=None, name="Tab", url="", threshold=None, resume_delay=None, auto_monitor=False):
        super().__init__(parent)
        self.parent = parent
        self.tab_name = name
        self.threshold = threshold or 5
        self.url = url
        self.monitoring = auto_monitor
        self.empty_scans = 0
        self.resume_delay = resume_delay or 1
        self.is_flashing = False
        self.flash_state = False
        self.paused = False

        self.layout = QVBoxLayout(self)

        # Top bar
        top_bar = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setText(url)
        self.load_button = QPushButton("Load")
        self.monitor_button = QPushButton("Start Monitor")
        self.load_button.clicked.connect(self.load_url)
        self.monitor_button.clicked.connect(self.toggle_monitoring)

        self.threshold_label = QLabel("Threshold:")
        self.threshold_dropdown = QComboBox()
        self.threshold_dropdown.addItems([str(i) for i in range(1, 11)])
        self.threshold_dropdown.setCurrentText(str(self.threshold))
        self.threshold_dropdown.currentTextChanged.connect(self.update_threshold)

        self.delay_label = QLabel("Delay Before Resuming (min):")
        self.delay_dropdown = QComboBox()
        self.delay_dropdown.addItems([str(i) for i in range(1, 21)])
        self.delay_dropdown.setCurrentText(str(self.resume_delay))
        self.delay_dropdown.currentTextChanged.connect(self.update_resume_delay)

        top_bar.addWidget(self.url_input)
        top_bar.addWidget(self.load_button)
        top_bar.addWidget(self.monitor_button)
        top_bar.addWidget(self.threshold_label)
        top_bar.addWidget(self.threshold_dropdown)
        top_bar.addWidget(self.delay_label)
        top_bar.addWidget(self.delay_dropdown)

        self.layout.addLayout(top_bar)

        self.browser = QWebEngineView()
        self.layout.addWidget(self.browser)
        self.layout.setStretch(1, 80)

        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.check_page)

        self.reload_timer = QTimer()
        self.reload_timer.timeout.connect(self.reload_page)

        self.flash_timer = QTimer()
        self.flash_timer.timeout.connect(self.flash_tab_icon)

        self.icon_paths = {
            "green": "green_icon.png",
            "red": "red_icon.png",
            "black": "black_icon.png"
        }

        self.set_icon("red")
        self.reload_timer.start(120000) #force reload interval

    def log(self, message):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{self.tab_name}] {message}")

    def load_url(self):
        self.url = self.url_input.text().strip()
        if not self.url.startswith("http"):
            self.url = "https://" + self.url
        self.browser.load(QUrl(self.url))
        self.log(f"Page loaded: {self.url}")

    def reload_page(self):
        self.browser.page().urlChanged.connect(self.update_current_url)
        self.browser.reload()
        self.log("Forced page reload.")

    def update_current_url(self, qurl):
        self.url = qurl.toString()
        self.url_input.setText(self.url)
        self.log(f"Updated URL to: {self.url}")

    def check_page(self):
        self.browser.page().toPlainText(self.process_text)

    def process_text(self, text):
        count = text.count("ACCEPTED") - 1
        self.log(f"'OPEN ORDERS' found: {count}")
        if count >= self.threshold:
            self.notify(count)
            self.pause_monitoring(self.resume_delay * 60)
        elif count == 0:
            self.empty_scans += 1
            if self.empty_scans >= 10:
                self.log("No 'ACCEPTED' in 10 scans. Pausing 3 minutes.")
                self.pause_monitoring(180) # interval for fail-scan
                self.empty_scans = 0
        else:
            self.empty_scans = 0

    def notify(self, count):
        self.play_sound()
        total_minutes = (count+1) * 18
        hours, minutes = divmod(total_minutes, 60)
        formatted_duration = f"{hours:02}:{minutes:02}"
        notification.notify(
            title=f"[{self.tab_name}] OPEN ORDERS",
            message = f"COUNT: ({count} Orders).\nSuggested Offline-Duration: {formatted_duration}",
            timeout=20
        )
        self.log(f"Notification triggered at {count} matches.")

    def play_sound(self):
        if platform.system() == "Windows":
            winsound.MessageBeep()
        else:
            subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"])

    def toggle_monitoring(self):
        if not self.monitoring:
            self.start_monitoring()
        else:
            self.stop_monitoring()

    def start_monitoring(self):
        self.monitor_timer.start(5000) #scan interval
        self.monitoring = True
        self.paused = False
        self.monitor_button.setText("Stop Monitor")
        self.start_flashing("green")
        self.log("Monitoring started.")

    def stop_monitoring(self):
        self.monitor_timer.stop()
        self.monitoring = False
        self.paused = False
        self.stop_flashing()
        self.set_icon("red")
        self.monitor_button.setText("Start Monitor")
        self.log("Monitoring stopped.")

    def pause_monitoring(self, seconds):
        self.stop_flashing()
        self.set_icon("black")
        self.monitor_timer.stop()
        self.paused = True
        QTimer.singleShot(seconds * 1000, self.resume_monitoring)
        self.log(f"Paused for {seconds // 60} min.")

    def resume_monitoring(self):
        self.paused = False
        self.monitor_timer.start(5000)
        self.start_flashing("green")
        self.log("Monitoring resumed.")
        notification.notify(
            title=f"[{self.tab_name}] Monitoring Resumed",
            message=f"PLEASE CHECK [{self.tab_name}]",
            timeout=10 #pause notification duration
        )

    def update_threshold(self, value):
        self.threshold = int(value)
        self.log(f"Threshold updated to {self.threshold}")

    def update_resume_delay(self, value):
        self.resume_delay = int(value)
        self.log(f"Resume delay updated to {self.resume_delay} minutes.")

    def start_flashing(self, color="green"):
        self.flashing_color = color
        self.is_flashing = True
        self.flash_state = False
        self.flash_timer.start(500)

    def stop_flashing(self):
        self.is_flashing = False
        self.flash_timer.stop()

    def flash_tab_icon(self):
        if not self.is_flashing:
            return
        color = "red" if self.flash_state else self.flashing_color
        self.set_icon(color)
        self.flash_state = not self.flash_state

    def set_icon(self, color):
        index = self.parent.tabs.indexOf(self)
        icon = QIcon(self.icon_paths.get(color, "green_icon.png"))
        self.parent.tabs.setTabIcon(index, icon)
        self.parent.tabs.setTabText(index, self.tab_name)

    def get_state(self):
        return {
            "name": self.tab_name,
            "url": self.url_input.text(),
            "threshold": self.threshold,
            "resume_delay": self.resume_delay,
            "auto_monitor": False  # Never auto-monitor on startup now
        }


class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Web Monitor")
        self.setGeometry(100, 100, 1200, 800)
        self.tabs = QTabWidget()
        self.tabs.setMovable(True)
        self.tabs.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.show_context_menu)
        self.setCentralWidget(self.tabs)
        self.load_tabs()

        # Global controls
        self.global_buttons_layout = QHBoxLayout()
        self.global_load_button = QPushButton("Load All Tabs")
        self.global_monitor_button = QPushButton("Start Monitor All")
        self.global_reload_button = QPushButton("Reload All Tabs")
        self.global_load_button.clicked.connect(self.load_all_tabs)
        self.global_monitor_button.clicked.connect(self.toggle_global_monitoring)
        self.global_reload_button.clicked.connect(self.reload_all_tabs)

        self.global_threshold_label = QLabel("Global Threshold:")
        self.global_threshold_dropdown = QComboBox()
        self.global_threshold_dropdown.addItems([str(i) for i in range(1,11)])
        self.global_threshold_dropdown.setCurrentText("5")
        self.global_threshold_dropdown.currentTextChanged.connect(self.set_all_thresholds)

        self.global_delay_label = QLabel("Global Delay (min):")
        self.global_delay_dropdown = QComboBox()
        self.global_delay_dropdown.addItems([str(i) for i in range(1, 21)])
        self.global_delay_dropdown.setCurrentText("1")
        self.global_delay_dropdown.currentTextChanged.connect(self.set_all_delays)

        self.global_buttons_layout.addWidget(self.global_load_button)
        self.global_buttons_layout.addWidget(self.global_monitor_button)
        self.global_buttons_layout.addWidget(self.global_reload_button)
        self.global_buttons_layout.addWidget(self.global_threshold_label)
        self.global_buttons_layout.addWidget(self.global_threshold_dropdown)
        self.global_buttons_layout.addWidget(self.global_delay_label)
        self.global_buttons_layout.addWidget(self.global_delay_dropdown)

        self.global_buttons_widget = QWidget()
        self.global_buttons_widget.setLayout(self.global_buttons_layout)
        self.setMenuWidget(self.global_buttons_widget)

    def toggle_global_monitoring(self):
        if self.global_monitor_button.text().startswith("Start"):
            self.start_all_monitoring()
            self.global_monitor_button.setText("Stop Monitor All")
        else:
            self.stop_all_monitoring()
            self.global_monitor_button.setText("Start Monitor All")

    def set_all_thresholds(self, value):
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            widget.threshold_dropdown.setCurrentText(value)

    def set_all_delays(self, value):
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            widget.delay_dropdown.setCurrentText(value)

    def add_tab(self, name="Tab", url="", threshold=5, resume_delay=1, auto_monitor=False):
        tab = MonitorTab(self, name, url, threshold, resume_delay, auto_monitor)
        index = self.tabs.addTab(tab, tab.tab_name)
        tab.set_icon("green" if auto_monitor else "red")
        self.tabs.setCurrentIndex(index)

    def show_context_menu(self, position):
        index = self.tabs.tabBar().tabAt(position)
        menu = QMenu()

        if index != -1:
            rename_action = menu.addAction("Rename Tab")
            close_action = menu.addAction("Close Tab")
            add_action = menu.addAction("Add Tab")
            action = menu.exec_(self.tabs.mapToGlobal(position))

            if action == rename_action:
                name, ok = QInputDialog.getText(self, "Rename Tab", "New tab name:")
                if ok and name:
                    self.tabs.setTabText(index, name)
                    widget = self.tabs.widget(index)
                    widget.tab_name = name
            elif action == close_action:
                self.tabs.removeTab(index)
            elif action == add_action:
                self.add_tab(name=f"Tab {self.tabs.count() + 1}")
        else:
            add_action = menu.addAction("Add Tab")
            action = menu.exec_(self.tabs.mapToGlobal(position))
            if action == add_action:
                self.add_tab(name=f"Tab {self.tabs.count() + 1}")

    def load_all_tabs(self):
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if widget.url.strip():
                widget.load_url()

    def start_all_monitoring(self):
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            widget.start_monitoring()

    def stop_all_monitoring(self):
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            widget.stop_monitoring()

    def reload_all_tabs(self):
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            widget.reload_page()

    def closeEvent(self, event):
        self.stop_all_monitoring()
        self.save_tabs()
        event.accept()

    def save_tabs(self):
        data = []
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            data.append(widget.get_state())
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print("[CONFIG] Tabs saved.")

    def load_tabs(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                for tab_data in data:
                    self.add_tab(**tab_data)
        else:
            self.add_tab(name="Tab 1")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec_())
