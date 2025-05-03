# Lightweight version: Web Monitor (streamlined)
import sys
import os
import json
import re
import platform
import webbrowser
import traceback
from datetime import datetime, timedelta
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtWidgets import QListWidget
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QLineEdit, QPushButton, QHBoxLayout, QInputDialog, QMenu, QComboBox, QLabel
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from plyer import notification
import pygame

CONFIG_FILE = "tabs_config.json"
PROFILE_PATH = os.path.join(os.getcwd(), "browser_profile")
ICON_PATHS = {"green": "green_icon.png", "red": "red_icon.png", "black": "black_icon.png"}
SCAN_INTERVAL = 15000
RELOAD_INTERVAL = 180000

if platform.system() != "Windows":
    os.environ["QT_QPA_PLATFORM"] = "wayland"

# Setup error logging
LOG_FILE = "monitor.log"
sys.excepthook = lambda exctype, value, tb: open(LOG_FILE, "a").write(
    f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] Uncaught Exception:\n" +
    "".join(traceback.format_exception(exctype, value, tb)) + "\n")

class MonitorTab(QWidget):
    def __init__(self, parent, name="Tab", url="", threshold=5, resume_delay=1):
        super().__init__(parent)
        self.parent = parent
        self.tab_name = name
        self.url = url
        self.threshold = threshold
        self.resume_delay = resume_delay
        self.monitoring = False
        self.paused = False
        self.page_ready = False

        self.layout = QVBoxLayout(self)
        self.init_ui()
        self.init_timers()

    def init_ui(self):
        top_bar = QHBoxLayout()
        self.url_input = QLineEdit(self.url)
        self.load_button = QPushButton("Load")
        self.monitor_button = QPushButton("Start Monitor")
        self.threshold_dropdown = QComboBox()
        self.delay_dropdown = QComboBox()
        self.threshold_dropdown.currentTextChanged.connect(lambda v: setattr(self, 'threshold', int(v)))

        self.threshold_dropdown.addItems(map(str, range(1, 11)))
        self.threshold_dropdown.setCurrentText(str(self.threshold))
        self.delay_dropdown.addItems(map(str, range(1, 21)))
        self.delay_dropdown.setCurrentText(str(self.resume_delay))
        self.delay_dropdown.currentTextChanged.connect(lambda v: setattr(self, 'resume_delay', int(v)))

        for widget in [self.url_input, self.load_button, self.monitor_button,
                       QLabel("Threshold:"), self.threshold_dropdown,
                       QLabel("Delay (min):"), self.delay_dropdown]:
            top_bar.addWidget(widget)

        self.browser = QWebEngineView()
        self.browser.setPage(self.parent.create_browser_page())
        self.browser.loadFinished.connect(self.on_load_finished)
        self.browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.browser.customContextMenuRequested.connect(self.context_menu)

        self.url_input.textChanged.connect(lambda: setattr(self, 'url', self.url_input.text().strip()))
        self.load_button.clicked.connect(self.load_url)
        self.monitor_button.clicked.connect(self.toggle_monitoring)

        self.layout.addLayout(top_bar)
        self.layout.addWidget(self.browser)

    def init_timers(self):
        self.empty_scan_count = 0
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.scan_page)
        self.reload_timer = QTimer(self)
        self.reload_timer.timeout.connect(self.reload_page)
        self.reload_timer.start(RELOAD_INTERVAL)

    def load_url(self):
        self.url = self.url_input.text().strip()
        if not self.url.startswith("http"):
            self.url = "https://" + self.url
        self.url_input.setText(self.url)
        self.page_ready = False
        self.browser.load(QUrl(self.url))

    def reload_page(self):
        self.page_ready = False
        if self.monitoring:
            self.monitor_timer.stop()
        injected_url, _ = self.parent._inject_date_range(self.url)
        self.url = injected_url
        self.url_input.setText(self.url)
        self.browser.load(QUrl(self.url))

    def scan_page(self):
        if self.page_ready:
            self.browser.page().toPlainText(self.process_text)

    def process_text(self, text):
        raw_count = text.count("ACCEPTED")
        count = max(0, raw_count - 1)
        if count >= self.threshold:
            self.alert_user(count)
            # log threshold reached
            total_minutes = count * 10
            h, m = divmod(total_minutes, 60)
            self.parent.log_event(f"Warning: [{self.tab_name}] order: {count} \nSuggestedd Offline: {h:02}:{m:02}")
            self.pause_monitoring(self.resume_delay * 60)
            self.empty_scan_count = 0
        elif count == 0 and self.monitoring and not self.paused:
            self.empty_scan_count += 1
            if self.empty_scan_count >= 5:
                index = self.parent.tabs.indexOf(self)
                self.parent.tabs.tabBar().setTabTextColor(index, Qt.GlobalColor.yellow)
                self.parent.tabs.tabBar().setStyleSheet("QTabBar::tab:selected { background-color: goldenrod; color: white; }")
                # log auto-pause due to zero scans
                self.parent.log_event(f"[{self.tab_name}] Paused, No Order \n Resume monitor after 3 Minutes")
                self.pause_monitoring(180)
                self.empty_scan_count = 0
        else:
            self.empty_scan_count = 0

    def alert_user(self, count):
        index = self.parent.tabs.indexOf(self)
        self.parent.tabs.tabBar().setTabTextColor(index, Qt.GlobalColor.red)
        self.parent.tabs.tabBar().setStyleSheet("QTabBar::tab:selected { background-color: darkred; color: white; }")
        try:
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.abspath(".")

            sound_path = os.path.join(base_path, "alert.mp3")
            if os.path.exists(sound_path):
                pygame.mixer.init()
                pygame.mixer.music.load(sound_path)
                pygame.mixer.music.play()
        except:
            pass

        total_minutes = count * 10
        h, m = divmod(total_minutes, 60)

        try:
            notification.notify(
                title=f"[{self.tab_name}] OPEN ORDERS",
                message=f"COUNT: {count}\nSuggestedd Offline: {h:02}:{m:02}", timeout=15)
        except:
            pass

    def toggle_monitoring(self):
        index = self.parent.tabs.indexOf(self)
        tab_bar = self.parent.tabs.tabBar()
        if self.monitoring:
            self.monitor_timer.stop()
            self.monitor_button.setText("Start Monitor")
            tab_bar.setTabTextColor(index, Qt.GlobalColor.white)
            tab_bar.setStyleSheet("QTabBar::tab:selected { background-color: none; color: white; }")
        else:
            self.monitor_timer.start(SCAN_INTERVAL)
            self.monitor_button.setText("Stop Monitor")
            tab_bar.setTabTextColor(index, Qt.GlobalColor.darkGreen)
            tab_bar.setStyleSheet("QTabBar::tab:selected { background-color: darkgreen; color: white; }")
        self.monitoring = not self.monitoring
        self.parent.update_monitor_button_state()

    def pause_monitoring(self, seconds):
        self.monitor_timer.stop()
        self.paused = True
        QTimer.singleShot(seconds * 1000, self.resume_monitoring)

    def resume_monitoring(self):
        self.paused = False
        if self.monitoring:
            self.monitor_timer.start(SCAN_INTERVAL)
            index = self.parent.tabs.indexOf(self)
            self.parent.tabs.tabBar().setTabTextColor(index, Qt.GlobalColor.darkGreen)
            self.parent.tabs.tabBar().setStyleSheet("QTabBar::tab:selected { background-color: darkgreen; color: white; }")

    def on_load_finished(self, ok):
        self.page_ready = ok

    def context_menu(self, pos):
        menu = QMenu()
        order = menu.addAction("Open Order Details")
        backoffice = menu.addAction("Backoffice")
        selected = menu.exec(self.browser.mapToGlobal(pos))
        if selected == order:
            self.browser.page().runJavaScript("window.getSelection().toString();", self.open_order_detail)
        elif selected == backoffice:
            self.parent.open_backoffice_url(self.parent.tabs.indexOf(self))

    def open_order_detail(self, text):
        text = text.strip().lower()
        if re.fullmatch(r"[a-z0-9]{4}-\d{4}-[a-z0-9]{4}", text):
            url = f"https://at.eu.logisticsbackoffice.com/dashboard/v2/hurrier/order_details/{text}"
            webbrowser.open(url)

    def get_state(self):
        return dict(name=self.tab_name, url=self.url_input.text(), threshold=self.threshold, resume_delay=self.resume_delay)


class MainApp(QMainWindow):
    def update_monitor_button_state(self):
        if all(self.tabs.widget(i).monitoring for i in range(self.tabs.count())):
            self.monitor_btn.setText("Stop Monitor All")
        else:
            self.monitor_btn.setText("Start Monitor All")

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Web Monitor")
        self.setGeometry(100, 100, 1200, 800)
        # — replace single-widget central with a split: tabs on left, log on right —
        container = QWidget()
        hlayout = QHBoxLayout(container)
        # configure the tab widget
        self.tabs = QTabWidget()
        self.tabs.setMovable(True)
        self.tabs.setStyleSheet("QTabBar::tab { max-width: 80px; }")
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.context_menu)

        # create the right-hand log list
        self.log_list = QListWidget()
        self.log_list.setWindowTitle("Event Log")
        self.log_list.setMaximumWidth(300)

        # assemble
        hlayout.addWidget(self.tabs)
        hlayout.addWidget(self.log_list)
        self.setCentralWidget(container)
        
        self.persistent_profile = self.create_profile()
        self.init_controls()
        self.load_tabs()


    def log_event(self, message):
        """Append timestamped message to the right-hand log list."""
        #ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_list.addItem(f"{ts} {message}")

    def create_profile(self):
        os.makedirs(PROFILE_PATH, exist_ok=True)
        profile = QWebEngineProfile("Persistent", self)
        profile.setPersistentStoragePath(PROFILE_PATH)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        return profile

    def create_browser_page(self):
        return QWebEnginePage(self.persistent_profile, self)

    def set_all_thresholds(self, value):
        for i in range(self.tabs.count()):
            self.tabs.widget(i).threshold_dropdown.setCurrentText(value)

    def set_all_delays(self, value):
        for i in range(self.tabs.count()):
            self.tabs.widget(i).delay_dropdown.setCurrentText(value)

    def init_controls(self):
        layout = QHBoxLayout()
        self.load_btn = QPushButton("Load All")
        self.monitor_btn = QPushButton("Start Monitor All")

        self.global_threshold_dropdown = QComboBox()
        self.global_threshold_dropdown.addItems([str(i) for i in range(1, 11)])
        self.global_threshold_dropdown.setCurrentText("5")
        self.global_threshold_dropdown.currentTextChanged.connect(self.set_all_thresholds)

        self.global_delay_dropdown = QComboBox()
        self.global_delay_dropdown.addItems([str(i) for i in range(1, 21)])
        self.global_delay_dropdown.setCurrentText("1")
        self.global_delay_dropdown.currentTextChanged.connect(self.set_all_delays)

        layout.addWidget(self.load_btn)
        layout.addWidget(self.monitor_btn)
        layout.addWidget(QLabel("Global Threshold:"))
        layout.addWidget(self.global_threshold_dropdown)
        layout.addWidget(QLabel("Global Delay (min):"))
        layout.addWidget(self.global_delay_dropdown)

        wrap = QWidget()
        wrap.setLayout(layout)
        self.setMenuWidget(wrap)
        self.load_btn.clicked.connect(self.load_all_tabs)
        self.monitor_btn.clicked.connect(self.toggle_all_monitoring)

    def add_tab(self, name="Tab", url="", threshold=5, resume_delay=1):
        tab = MonitorTab(self, name, url, threshold, resume_delay)
        index = self.tabs.addTab(tab, tab.tab_name)
        self.tabs.setCurrentIndex(index)
        # immediately apply the current global values to this new tab:
        tab.threshold_dropdown.setCurrentText(self.global_threshold_dropdown.currentText())
        tab.delay_dropdown.setCurrentText(self.global_delay_dropdown.currentText())
        return tab

    def load_all_tabs(self):
        for i in range(self.tabs.count()):
            self.tabs.widget(i).load_url()

    def toggle_all_monitoring(self):
        all_running = all(self.tabs.widget(i).monitoring for i in range(self.tabs.count()))
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if all_running and tab.monitoring:
                tab.toggle_monitoring()
            elif not all_running and not tab.monitoring:
                tab.toggle_monitoring()
        self.update_monitor_button_state()

    def context_menu(self, pos):
        index = self.tabs.tabBar().tabAt(pos)
        menu = QMenu()
        rename_action = menu.addAction("Rename")
        close_action = menu.addAction("Close")
        add_action = menu.addAction("Add Tab")
        selected = menu.exec(self.tabs.mapToGlobal(pos))
        if selected == rename_action and index != -1:
            name, ok = QInputDialog.getText(self, "Rename Tab", "New name:")
            if ok:
                self.tabs.setTabText(index, name)
                self.tabs.widget(index).tab_name = name
        elif selected == close_action and index != -1:
            self.tabs.removeTab(index)
        elif selected == add_action:
            self.add_tab(name=f"Tab {self.tabs.count() + 1}")

    def _inject_date_range(self, url):
        if not url.startswith("http"): url = "https://" + url
        today = datetime.combine(datetime.today(), datetime.strptime("12:00PM", "%I:%M%p").time())
        start = int((today - timedelta(days=1)).timestamp() * 1000)
        end = int(today.timestamp() * 1000)
        url = re.sub(r"(updates_list_dateRange\[\]=)[^&]*", "", url)
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}updates_list_dateRange[]={start},{end}", True

    def open_backoffice_url(self, index):
        tab = self.tabs.widget(index)
        match = re.search(r"updates_list_outlets\[]=(\w+)", tab.url_input.text())
        if match:
            code = match.group(1)[-4:]
            url = f"https://portal.foodora.com/pv2/at/p/backoffice/vendors/{code}"
            webbrowser.open(url)

    def load_tabs(self):
        if not os.path.exists(CONFIG_FILE):
            self.add_tab(name="Tab 1")
            return
        with open(CONFIG_FILE, "r") as f:
            for data in json.load(f):
                filtered_data = {k: v for k, v in data.items() if k in ['name', 'url', 'threshold', 'resume_delay']}
                tab = self.add_tab(**filtered_data)
                tab.load_url()

    def closeEvent(self, event):
        with open(CONFIG_FILE, "w") as f:
            json.dump([self.tabs.widget(i).get_state() for i in range(self.tabs.count())], f)
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainApp()
    win.show()
    sys.exit(app.exec())
