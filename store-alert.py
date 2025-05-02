import sys
import json
import os
import platform
from datetime import datetime, timedelta
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QLineEdit, QPushButton, QHBoxLayout, QInputDialog, QMenu, QComboBox, QLabel
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from plyer import notification
import logging
import re
import pygame

# Constants
CONFIG_FILE = "tabs_config.json"
PROFILE_PATH = os.path.join(os.getcwd(), "browser_profile")
ICON_PATHS = {"green": "green_icon.png", "red": "red_icon.png", "black": "black_icon.png"}
SCAN_INTERVAL = 15000
RELOAD_INTERVAL = 180000
MAX_EMPTY_SCANS = 10
PAUSE_ON_EMPTY_SECONDS = 180

if platform.system() != "Windows":
    os.environ["QT_QPA_PLATFORM"] = "wayland"
logging.basicConfig(level=logging.ERROR)
if platform.system() == "Windows":
    import winsound


class MonitorTab(QWidget):
    def __init__(self, parent=None, name="Tab", url="", threshold=5, resume_delay=1, auto_monitor=False):
        super().__init__(parent)
        self.parent = parent
        self.tab_name = name
        self.url = url
        self.threshold = threshold
        self.resume_delay = resume_delay
        self.monitoring = auto_monitor
        self.paused = False
        self.empty_scans = 0
        self.is_flashing = False
        self.flash_state = False
        self.page_ready = False

        self.layout = QVBoxLayout(self)
        self.setup_ui()
        self.setup_timers()

    def setup_ui(self):
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
        self.threshold_dropdown.currentTextChanged.connect(lambda v: self.update_config("threshold", v))

        self.delay_dropdown.addItems([str(i) for i in range(1, 21)])
        self.delay_dropdown.setCurrentText(str(self.resume_delay))
        self.delay_dropdown.currentTextChanged.connect(lambda v: self.update_config("resume_delay", v))

        for widget in [self.url_input, self.load_button, self.monitor_button, self.threshold_label,
                       self.threshold_dropdown, self.delay_label, self.delay_dropdown]:
            top_bar.addWidget(widget)
        self.layout.addLayout(top_bar)

        self.browser = QWebEngineView()
        self.browser.setPage(self.parent.create_browser_page())
        self.layout.addWidget(self.browser)
        self.browser.loadFinished.connect(self.on_load_finished)
        self.browser.urlChanged.connect(self.on_browser_url_changed)

        self.load_button.clicked.connect(self.load_url)
        self.monitor_button.clicked.connect(self.toggle_monitoring)
        self.url_input.textChanged.connect(self.on_url_changed)

    def setup_timers(self):
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.check_page)
        self.reload_timer = QTimer(self)
        self.reload_timer.timeout.connect(self.reload_page)
        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self.flash_tab_icon)

        self.monitor_timer.setSingleShot(False)
        self.reload_timer.start(RELOAD_INTERVAL)
        self.set_icon("red")

    def log(self, message):
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{self.tab_name}] {message}")

    def load_url(self):
        self.url = self.url_input.text().strip()
        if not self.url.startswith("http"):
            self.url = "https://" + self.url
        self.page_ready = False
        self.url_input.setText(self.url)
        self.browser.load(QUrl(self.url))

    def reload_page(self):
        self.page_ready = False
        if self.monitoring:
            self.monitor_timer.stop()
        self.url, _ = self.parent._inject_date_range(self.url)
        self.url_input.setText(self.url)
        self.browser.load(QUrl(self.url))
        self.log("Forced page reload with fresh date range.")

    def check_page(self):
        if not self.page_ready:
            self.log("Page not ready, skipping scan.")
            return
        self.browser.page().toPlainText(self.process_text)

    def process_text(self, text):
        count = text.count("ACCEPTED") - 1
        self.log(f"'OPEN ORDERS' found: {count}")
        if count >= self.threshold:
            self.notify(count)
            self.pause_monitoring(self.resume_delay * 60)
        elif count == 0:
            self.empty_scans += 1
            if self.empty_scans >= MAX_EMPTY_SCANS:
                self.log("No 'ACCEPTED' in 10 scans. Pausing 3 minutes.")
                self.pause_monitoring(PAUSE_ON_EMPTY_SECONDS)
                self.empty_scans = 0
        else:
            self.empty_scans = 0

    def notify(self, count):
        self.play_sound()
        total_minutes = (count + 1) * 18
        hours, minutes = divmod(total_minutes, 60)
        notification.notify(
            title=f"[{self.tab_name}] OPEN ORDERS",
            message=f"COUNT: ({count} Orders).\nSuggested Offline-Duration: {hours:02}:{minutes:02}",
            timeout=20
        )
        self.log(f"Notification triggered at {count} matches.")

    def play_sound(self):
        sound_file = "alert.mp3"
        if os.path.exists(sound_file):
            try:
                pygame.mixer.init()
                pygame.mixer.music.load(sound_file)
                pygame.mixer.music.play()
            except Exception as e:
                print(f"Error playing sound: {e}")

    def toggle_monitoring(self):
        if self.monitoring:
            self.stop_monitoring()
        else:
            self.start_monitoring()

    def start_monitoring(self):
        self.monitoring = True
        self.paused = False
        self.monitor_button.setText("Stop Monitor")
        self.start_flashing("green")
        self.monitor_timer.start(SCAN_INTERVAL)
        self.log("Monitoring started.")

    def stop_monitoring(self):
        self.monitoring = False
        self.paused = False
        self.stop_flashing()
        self.monitor_timer.stop()
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
        self.monitor_timer.start(SCAN_INTERVAL)
        self.start_flashing("green")
        self.log("Monitoring resumed.")

    def update_config(self, key, value):
        if key == "threshold":
            self.threshold = int(value)
        elif key == "resume_delay":
            self.resume_delay = int(value)
        self.log(f"{key.replace('_', ' ').capitalize()} updated to {value}")

    def start_flashing(self, color="green"):
        self.flashing_color = color
        self.is_flashing = True
        self.flash_state = False
        self.flash_timer.start(500)

    def stop_flashing(self):
        self.is_flashing = False
        self.flash_timer.stop()

    def flash_tab_icon(self):
        if self.is_flashing:
            color = "red" if self.flash_state else self.flashing_color
            self.set_icon(color)
            self.flash_state = not self.flash_state

    def set_icon(self, color):
        index = self.parent.tabs.indexOf(self)
        icon = QIcon(ICON_PATHS.get(color, "green_icon.png"))
        self.parent.tabs.setTabIcon(index, icon)
        self.parent.tabs.setTabText(index, self.tab_name)

    def get_state(self):
        return {
            "name": self.tab_name,
            "url": self.url_input.text(),
            "threshold": self.threshold,
            "resume_delay": self.resume_delay,
            "auto_monitor": False
        }

    def on_url_changed(self):
        self.url = self.url_input.text().strip()

    def on_browser_url_changed(self, qurl):
        self.url_input.setText(qurl.toString())

    def on_load_finished(self, success):
        self.page_ready = success
        if success and self.monitoring and not self.monitor_timer.isActive() and not self.paused:
            self.monitor_timer.start(SCAN_INTERVAL)
            self.log("Monitoring resumed after page load.")
        elif not success:
            self.log("Page failed to load.")

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Web Monitor")
        self.setGeometry(100, 100, 1200, 800)
        self.tabs = QTabWidget(self)
        self.tabs.setMovable(True)
        self.tabs.setStyleSheet("QTabBar::tab { max-width: 80px; }")
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.show_context_menu)
        self.setCentralWidget(self.tabs)

        self.persistent_profile = self.create_persistent_profile()  # <-- Important

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

        self.load_tabs()

    def create_persistent_profile(self):
        os.makedirs(PROFILE_PATH, exist_ok=True)
        profile = QWebEngineProfile("PersistentProfile", self)
        profile.setPersistentStoragePath(PROFILE_PATH)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        return profile

    def create_browser_page(self):
        return QWebEnginePage(self.persistent_profile, self)

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

    

    def show_context_menu(self, position):
        index = self.tabs.tabBar().tabAt(position)
        menu = QMenu()
        if index != -1:
            rename_action = menu.addAction("Rename Tab")
            close_action = menu.addAction("Close Tab")
            add_action = menu.addAction("Add Tab")
            action = menu.exec(self.tabs.mapToGlobal(position))
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
            action = menu.exec(self.tabs.mapToGlobal(position))
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

    def save_tabs(self):
        data = [widget.get_state() for widget in (self.tabs.widget(i) for i in range(self.tabs.count()))]
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print("[CONFIG] Tabs saved.")


    def closeEvent(self, event):
        self.stop_all_monitoring()
        self.save_tabs()
        event.accept()

    def add_tab(self, name="Tab", url="", threshold=5, resume_delay=1, auto_monitor=False):
        if url:
            url, _ = self._inject_date_range(url)
        tab = MonitorTab(self, name, url, threshold, resume_delay, auto_monitor)
        index = self.tabs.addTab(tab, tab.tab_name)
        tab.set_icon("green" if auto_monitor else "red")
        self.tabs.setCurrentIndex(index)
        return tab


    def _inject_date_range(self, raw_url: str) -> tuple[str, bool]:
        from datetime import datetime, timedelta
        import re

        if not raw_url.startswith("http"):
            raw_url = "https://" + raw_url

        # Timestamps for yesterday and today at 12:00 PM
        noon_today = datetime.combine(datetime.now().date(), datetime.strptime("12:00:00PM", "%I:%M:%S%p").time())
        noon_yesterday = noon_today - timedelta(days=1)

        ts_start = int(noon_yesterday.timestamp() * 1000)
        ts_end = int(noon_today.timestamp() * 1000)

        #print(f"[DateRange Injection] Start: {noon_yesterday.strftime('%d.%m.%Y %H:%M')} ({ts_start})")
        #print(f"[DateRange Injection] End:   {noon_today.strftime('%d.%m.%Y %H:%M')} ({ts_end})")

        # Cleanup: remove all duplicate dateRange params
        url_cleaned = re.sub(r"(updates_list_dateRange\[\]=)[^&]*", "", raw_url)

        # Cleanup: remove lonely numbers (very likely garbage)
        url_cleaned = re.sub(r"[&?]?\d{13}(?:,\d{13})?", "", url_cleaned)

        # Remove double && or &? if needed
        url_cleaned = re.sub(r"[&?]+(?=&)", "", url_cleaned)
        url_cleaned = re.sub(r"[&?]+$", "", url_cleaned)

        # Add fresh param
        sep = "&" if "?" in url_cleaned else "?"
        updated_url = f"{url_cleaned}{sep}updates_list_dateRange[]={ts_start},{ts_end}"

        # Final cleanup (no trailing ampersand mess)
        updated_url = re.sub(r"[&]+", "&", updated_url)

        return updated_url, updated_url != raw_url



    def load_tabs(self):
        modified = False  # <-- Initialize the flag
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            for tab_data in data:
                # inject the date‐range right here
                injected_url, was_modified = self._inject_date_range(tab_data.get("url", ""))
                tab_data["url"] = injected_url
                if was_modified:
                    modified = True
                tab = self.add_tab(**tab_data)
                tab.load_url()
            
            # Save back only if any URL was modified
            if modified:
                self.save_tabs()
        else:
            # first runs still get a tab
            self.add_tab(name="Tab 1")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec())
