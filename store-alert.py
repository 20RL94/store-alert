import sys
import json
import os
import platform
from datetime import datetime
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QLineEdit, QPushButton, QHBoxLayout, QInputDialog, QMenu, QComboBox, QLabel
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from plyer import notification
import logging
import subprocess
import winsound

# Constants
CONFIG_FILE = "tabs_config.json"
ICON_PATHS = {
    "green": "green_icon.png",
    "red": "red_icon.png",
    "black": "black_icon.png"
}

# Suppress Wayland warning
if platform.system() != "Windows":
    os.environ["QT_QPA_PLATFORM"] = "wayland"

logging.basicConfig(level=logging.ERROR)

if platform.system() == "Windows":
    import winsound


class MonitorTab(QWidget):
    def __init__(self, parent=None, name="Tab", url="", threshold=None, resume_delay=None, auto_monitor=False):
        super().__init__(parent)
        self.parent = parent
        self.tab_name = name
        self.url = url
        self.threshold = threshold or 5
        self.resume_delay = resume_delay or 1
        self.monitoring = auto_monitor
        self.paused = False
        self.empty_scans = 0
        self.is_flashing = False
        self.flash_state = False

        self.layout = QVBoxLayout(self)
        self.setup_ui()
        self.setup_timers()
         # Detect URL change in the input field
        self.url_input.textChanged.connect(self.on_url_changed)

        # Listen to changes in the web view's URL
        self.browser.urlChanged.connect(self.on_browser_url_changed)
    
    def on_url_changed(self):
        """Detect URL change in the input field and update the browser QUrl."""
        new_url = self.url_input.text().strip()
        if new_url and new_url != self.url:
            if not new_url.startswith("http"):
                new_url = "https://" + new_url
            self.url = new_url
            self.browser.load(QUrl(new_url))  # Load the new URL in the browser
            self.log(f"URL updated to: {new_url}")

    def on_browser_url_changed(self, qurl):
        """Detect URL change in the browser and update the URL input field."""
        new_url = qurl.toString()
        if new_url != self.url_input.text():
            self.url_input.setText(new_url)  # Update the URL text in the input field
            self.url = new_url
            self.log(f"URL in browser updated to: {new_url}")
            
    def setup_ui(self):
        #Setup UI components for this tab.
        # Top bar
        top_bar = QHBoxLayout()
        self.url_input = QLineEdit(self.url)
        self.load_button = QPushButton("Load")
        self.monitor_button = QPushButton("Start Monitor")
        self.threshold_label = QLabel("Threshold:")
        self.threshold_dropdown = QComboBox()
        self.delay_label = QLabel("Delay Before Resuming (min):")
        self.delay_dropdown = QComboBox()

        self.threshold_dropdown.addItems([str(i) for i in range(1, 11)])
        self.threshold_dropdown.setCurrentText(str(self.threshold))
        self.threshold_dropdown.currentTextChanged.connect(self.update_threshold)

        self.delay_dropdown.addItems([str(i) for i in range(1, 21)])
        self.delay_dropdown.setCurrentText(str(self.resume_delay))
        self.delay_dropdown.currentTextChanged.connect(self.update_resume_delay)

        # Add widgets to top_bar
        top_bar.addWidget(self.url_input)
        top_bar.addWidget(self.load_button)
        top_bar.addWidget(self.monitor_button)
        top_bar.addWidget(self.threshold_label)
        top_bar.addWidget(self.threshold_dropdown)
        top_bar.addWidget(self.delay_label)
        top_bar.addWidget(self.delay_dropdown)

        self.layout.addLayout(top_bar)

        # Browser setup
        self.browser = QWebEngineView()
        self.layout.addWidget(self.browser)
        self.layout.setStretch(1, 80)

        # Buttons connections
        self.load_button.clicked.connect(self.load_url)
        self.monitor_button.clicked.connect(self.toggle_monitoring)

    def setup_timers(self):
        """Setup timers for page monitoring and flashing."""
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.check_page)
        self.reload_timer = QTimer(self)
        self.reload_timer.timeout.connect(self.reload_page)
        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self.flash_tab_icon)

        self.reload_timer.start(120000)  # Reload every 2 minutes
        self.set_icon("red")
        self.monitor_timer.setSingleShot(False)

    def log(self, message):
        """Log messages to the console with timestamp."""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{self.tab_name}] {message}")

    def load_url(self):
        """Load the URL in the browser."""
        self.url = self.url_input.text().strip()
        if not self.url.startswith("http"):
            self.url = "https://" + self.url
        self.browser.load(QUrl(self.url))
        self.log(f"Page loaded: {self.url}")

    def reload_page(self):
        """Reload the web page."""
        self.browser.reload()
        self.log("Forced page reload.")

    def check_page(self):
        """Check page content for specific keyword."""
        self.browser.page().toPlainText(self.process_text)

    def process_text(self, text):
        """Process the page text for 'ACCEPTED' occurrences."""
        count = text.count("ACCEPTED") - 1
        self.log(f"'OPEN ORDERS' found: {count}")
        if count >= self.threshold:
            self.notify(count)
            self.pause_monitoring(self.resume_delay * 60)
        elif count == 0:
            self.empty_scans += 1
            if self.empty_scans >= 10:
                self.log("No 'ACCEPTED' in 10 scans. Pausing 3 minutes.")
                self.pause_monitoring(180)
                self.empty_scans = 0
        else:
            self.empty_scans = 0

    def notify(self, count):
        """Send system notification with the count."""
        self.play_sound()
        total_minutes = (count + 1) * 18
        hours, minutes = divmod(total_minutes, 60)
        formatted_duration = f"{hours:02}:{minutes:02}"
        notification.notify(
            title=f"[{self.tab_name}] OPEN ORDERS",
            message=f"COUNT: ({count} Orders).\nSuggested Offline-Duration: {formatted_duration}",
            timeout=20
        )
        self.log(f"Notification triggered at {count} matches.")

    def play_sound(self):
        """Play a sound on notification."""
        if platform.system() == "Windows":
            winsound.MessageBeep()
        else:
            subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"])

    def toggle_monitoring(self):
        """Toggle monitoring state."""
        if not self.monitoring:
            self.start_monitoring()
        else:
            self.stop_monitoring()

    def start_monitoring(self):
        """Start monitoring the page."""
        self.monitor_timer.start(5000)  # Scan every 5 seconds
        self.monitoring = True
        self.paused = False
        self.monitor_button.setText("Stop Monitor")
        self.start_flashing("green")
        self.log("Monitoring started.")

    def stop_monitoring(self):
        """Stop monitoring the page."""
        self.monitor_timer.stop()
        self.monitoring = False
        self.paused = False
        self.stop_flashing()
        self.set_icon("red")
        self.monitor_button.setText("Start Monitor")
        self.log("Monitoring stopped.")

    def pause_monitoring(self, seconds):
        """Pause the monitoring for a specific duration."""
        self.stop_flashing()
        self.set_icon("black")
        self.monitor_timer.stop()
        self.paused = True
        QTimer.singleShot(seconds * 1000, self.resume_monitoring)
        self.log(f"Paused for {seconds // 60} min.")

    def resume_monitoring(self):
        """Resume the monitoring after a pause."""
        self.paused = False
        self.monitor_timer.start(5000)
        self.start_flashing("green")
        self.log("Monitoring resumed.")
        notification.notify(
            title=f"[{self.tab_name}] Monitoring Resumed",
            message=f"PLEASE CHECK [{self.tab_name}]",
            timeout=15
        )

    def update_threshold(self, value):
        """Update the threshold for 'ACCEPTED' occurrences."""
        self.threshold = int(value)
        self.log(f"Threshold updated to {self.threshold}")

    def update_resume_delay(self, value):
        """Update the resume delay."""
        self.resume_delay = int(value)
        self.log(f"Resume delay updated to {self.resume_delay} minutes.")

    def start_flashing(self, color="green"):
        """Start flashing the tab icon with a color."""
        self.flashing_color = color
        self.is_flashing = True
        self.flash_state = False
        self.flash_timer.start(500)

    def stop_flashing(self):
        """Stop flashing the tab icon."""
        self.is_flashing = False
        self.flash_timer.stop()

    def flash_tab_icon(self):
        """Flash the tab icon between the color states."""
        if not self.is_flashing:
            return
        color = "red" if self.flash_state else self.flashing_color
        self.set_icon(color)
        self.flash_state = not self.flash_state

    def set_icon(self, color):
        """Set the tab icon based on the current state."""
        index = self.parent.tabs.indexOf(self)
        icon = QIcon(ICON_PATHS.get(color, "green_icon.png"))
        self.parent.tabs.setTabIcon(index, icon)
        self.parent.tabs.setTabText(index, self.tab_name)
    

    def get_state(self):
        """Get the state of the tab."""
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
        self.tabs = QTabWidget(self)
        self.tabs.setMovable(True)
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.show_context_menu)
        self.setCentralWidget(self.tabs)
        self.load_tabs()

        self.global_buttons_layout = QHBoxLayout()
        self.global_load_button = QPushButton("Load All Tabs")
        self.global_monitor_button = QPushButton("Start Monitor All")
        self.global_reload_button = QPushButton("Reload All Tabs")
        self.global_load_button.clicked.connect(self.load_all_tabs)
        self.global_monitor_button.clicked.connect(self.toggle_global_monitoring)
        self.global_reload_button.clicked.connect(self.reload_all_tabs)

        self.global_threshold_label = QLabel("Global Threshold:")
        self.global_threshold_dropdown = QComboBox()
        self.global_threshold_dropdown.addItems([str(i) for i in range(1, 11)])
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
        """Toggle global monitoring for all tabs."""
        if self.global_monitor_button.text().startswith("Start"):
            self.start_all_monitoring()
            self.global_monitor_button.setText("Stop Monitor All")
        else:
            self.stop_all_monitoring()
            self.global_monitor_button.setText("Start Monitor All")

    def set_all_thresholds(self, value):
        """Set the threshold for all tabs."""
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            widget.threshold_dropdown.setCurrentText(value)

    def set_all_delays(self, value):
        """Set the delay for all tabs."""
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            widget.delay_dropdown.setCurrentText(value)

    def add_tab(self, name="Tab", url="", threshold=5, resume_delay=1, auto_monitor=False):
        """Add a new tab to the application."""
        tab = MonitorTab(self, name, url, threshold, resume_delay, auto_monitor)
        index = self.tabs.addTab(tab, tab.tab_name)
        tab.set_icon("green" if auto_monitor else "red")
        self.tabs.setCurrentIndex(index)

    def show_context_menu(self, position):
        """Show context menu for managing tabs."""
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
        """Load all tabs' URLs."""
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if widget.url.strip():
                widget.load_url()

    def start_all_monitoring(self):
        """Start monitoring on all tabs."""
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            widget.start_monitoring()

    def stop_all_monitoring(self):
        """Stop monitoring on all tabs."""
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            widget.stop_monitoring()

    def reload_all_tabs(self):
        """Reload all tabs."""
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            widget.reload_page()

    def closeEvent(self, event):
        """Save tabs' state before closing."""
        self.stop_all_monitoring()
        self.save_tabs()
        event.accept()

    def save_tabs(self):
        """Save the current state of all tabs to a config file."""
        data = [widget.get_state() for widget in (self.tabs.widget(i) for i in range(self.tabs.count()))]
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print("[CONFIG] Tabs saved.")

    def load_tabs(self):
        """Load tabs from the config file if it exists."""
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
    sys.exit(app.exec())
