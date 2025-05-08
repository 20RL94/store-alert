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
from PyQt6.QtWidgets import QGraphicsOpacityEffect
from PyQt6.QtCore import QPropertyAnimation
from PyQt6.QtWidgets import QListWidgetItem
from plyer import notification
import pygame
def get_resource_path(filename):
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.abspath("."), filename)

 # determine a writable base directory (next to the exe when frozen)
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.abspath(".")
CONFIG_FILE  = os.path.join(BASE_DIR, "tabs_config.json")
LOG_FILE = os.path.join(BASE_DIR, "monitor.log")



SCAN_INTERVAL = 15000
RELOAD_INTERVAL = 180000

if platform.system() != "Windows":
    os.environ["QT_QPA_PLATFORM"] = "wayland"

# Setup error logging
sys.excepthook = lambda exctype, value, tb: open(LOG_FILE, "a").write(
    f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] Uncaught Exception:\n" +
    "".join(traceback.format_exception(exctype, value, tb)) + "\n")

class MonitorTab(QWidget):
    def __init__(self, parent, name="Tab", url="", threshold=5, resume_delay=1, max_order_price=100):
        super().__init__(parent)
        self.parent = parent
        self.tab_name = name
        self.url = url
        self.threshold = threshold
        self.resume_delay = resume_delay
        self.monitoring = False
        self.paused = False
        self.page_ready = False
        self.max_order_price = max_order_price

        self.original_url = url  # preserve the clean config URL
        self.layout = QVBoxLayout(self)
        self.init_ui()
        self.init_timers()
        self.last_price_alert_time = None


    def init_ui(self):
        top_bar = QHBoxLayout()
        self.url_input = QLineEdit(self.url)
        self.load_button = QPushButton("Load")
        self.monitor_button = QPushButton("Start Monitor")
        self.threshold_dropdown = QComboBox()
        self.delay_dropdown = QComboBox()

        self.threshold_dropdown.addItems(map(str, range(1, 11)))
        self.threshold_dropdown.setCurrentText(str(self.threshold))
        self.threshold_dropdown.currentTextChanged.connect(lambda v: setattr(self, 'threshold', int(v)))
        self.delay_dropdown.addItems(map(str, range(1, 21)))
        self.delay_dropdown.setCurrentText(str(self.resume_delay))
        self.delay_dropdown.currentTextChanged.connect(lambda v: setattr(self, 'resume_delay', int(v)))

        for widget in [self.url_input, self.load_button, self.monitor_button,
                       QLabel("Order:"), self.threshold_dropdown,
                       QLabel("Delay (min):"), self.delay_dropdown]:
            top_bar.addWidget(widget)

        self.browser = QWebEngineView()
        self.browser.setPage(QWebEnginePage(self.browser))
        self.browser.loadFinished.connect(self.on_load_finished)
        self.browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.browser.customContextMenuRequested.connect(self.context_menu)

        self.browser.urlChanged.connect(self.update_current_url)# url sync

        self.url_input.textChanged.connect(lambda: setattr(self, 'url', self.url_input.text().strip()))
        self.load_button.clicked.connect(lambda: self.load_url(use_original_url=False))
        self.monitor_button.clicked.connect(self.toggle_monitoring)

        self.layout.addLayout(top_bar)
        self.layout.addWidget(self.browser)
    
    def update_current_url(self, qurl):
        url = qurl.toString()
        if "redirect" not in url:
            self.url = url
            self.url_input.setText(url)


    def init_timers(self):
        self.empty_scan_count = 0
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.scan_page)
        self.reload_timer = QTimer(self)
        self.reload_timer.timeout.connect(self.reload_page)
        self.reload_timer.start(RELOAD_INTERVAL)

    def load_url(self, use_original_url=False):
        if use_original_url:
            self.url = self.original_url.strip()
        else:
            self.url = self.url_input.text().strip()

        self.url = self.url.replace("%00", "")
        if not self.url.startswith("http"):
            self.url = "https://" + self.url
        
        self.url_input.setText(self.url)
        self.page_ready = False
        self.browser.load(QUrl(self.url))

    def reload_page(self):
        self.page_ready = False
        if self.monitoring:
            self.monitor_timer.stop()

        injected_url, _ = self.parent._inject_date_range(self.original_url)
        self.url = injected_url.replace("%00", "")
        self.url_input.setText(self.url)
        self.browser.load(QUrl(self.url))

    def scan_page(self):
        if self.page_ready:
            # run JS to count rows where:
            #  - 4th cell text === "ACCEPTED"
            #  - 6th cell text is neither empty nor "-"
            js = f"""
            (function(){{
                const rows = Array.from(document.querySelectorAll('tr'))
                    .filter(row => row.className.includes('cape_table_row'));

                let totalCount = 0;
                let totalSum = 0;

                rows.forEach(row => {{
                    const cells = row.querySelectorAll('td');
                    if (cells.length > 8) {{
                        const status = cells[3].innerText.trim();
                        const col6   = cells[5].innerText.trim();
                        const priceText = cells[8].innerText.trim();
                        const leftText = priceText.split('|')[0].trim();
                        const leftPriceMatch = leftText.match(/EUR\\s+(\\d+\\.\\d+)/);
                        const price = leftPriceMatch ? parseFloat(leftPriceMatch[1]) : null;

                        if (status === 'ACCEPTED' && col6 !== '' && col6 !== '-' && price !== null) {{
                            totalCount++;
                            totalSum += price;
                        }}
                    }}
                }});

                const average = totalCount > 0 ? totalSum / totalCount : 0;
                return [totalCount, totalSum, average];
            }})();
            """
            self.browser.page().runJavaScript(js, self.handle_js_count)

    # new callback to receive JS count
    def handle_js_count(self, result):
        if not isinstance(result, list) or len(result) != 3:
            return

        total_count, total_sum ,avg = result
        avg_price = float(avg)

        # ✅ Price-limit notification only (textlist)
        if round(avg_price, 2) >= round(self.max_order_price, 2) and total_count > 0:
            now = datetime.now()
            if not self.last_price_alert_time or (now - self.last_price_alert_time).total_seconds() >= 120: #Pause for 2 minutes
                self.parent.log_event(
                    f"💶 {self.tab_name.upper()} Monitoring: {total_count} Order(s)\n"
                    f"{' ' * 17}AVG ORDER: €{avg_price:.2f}")
                self.last_price_alert_time = now
        # ✅ Threshold logic remains unchanged
        if total_count >= self.threshold:
            self.alert_user(total_count)
            total_minutes = total_count * 10
            h, m = divmod(total_minutes, 60)
            msg = (
                f"🛍️ {self.tab_name.upper()} has {total_count} order(s)\n"
                f"{' ' * 17}🕛 Suggested offline: {h:02}:{m:02}")
            self.parent.log_event(msg)
            self.pause_monitoring(self.resume_delay * 60)
            self.empty_scan_count = 0
        elif total_count == 0 and self.monitoring and not self.paused:
            self.empty_scan_count += 1
            if self.empty_scan_count >= 5:
                idx = self.parent.tabs.indexOf(self)
                self.parent.tabs.tabBar().setTabTextColor(idx, Qt.GlobalColor.yellow)
                self.parent.log_event(
                f"😴 {self.tab_name.upper()} has no orders\n"
                f"{' ' * 17}Check Tab for Error?")
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

            sound_path = get_resource_path("alert.mp3")
            if os.path.exists(sound_path):
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                sound = pygame.mixer.Sound(sound_path)
                sound.play()
        except:
            self.parent.log_event(f"Sound error: {e}")
            pass

        #total_minutes = count * 10
        #h, m = divmod(total_minutes, 60)
        #try:
        #    notification.notify(
        #        title=f"[{self.tab_name}] OPEN ORDERS",
        #        message=f"COUNT: {count}\nSuggestedd Offline: {h:02}:{m:02}", timeout=15)
        #except:
        #    pass

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
        if ok and self.monitoring and not self.monitor_timer.isActive() and not self.paused:
            self.monitor_timer.start(SCAN_INTERVAL)

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
        return dict(
        name=self.tab_name, 
        url=self.original_url, 
        threshold=self.threshold, 
        resume_delay=self.resume_delay,
        max_order_price=self.max_order_price)


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
        #self.log_list.itemDoubleClicked.connect(self.switch_to_tab_from_log)

        # assemble
        hlayout.addWidget(self.tabs)
        hlayout.addWidget(self.log_list)
        self.setCentralWidget(container)
        
        self.init_controls()
        self.load_tabs()



    def log_event(self, message):
        ts = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem()
        label_text = f"{ts} {message}"
        item.setData(Qt.ItemDataRole.UserRole, label_text)  # used by patch

        from clickable_label import ClickableLabel  # ✅ import your class
        label = ClickableLabel(label_text)
        label.doubleClicked.connect(lambda: self.switch_to_tab_from_text(label_text))

        label.setWordWrap(True)
        label.setContentsMargins(6, 6, 6, 6)
        label.setStyleSheet("font-size: 12px;")
        label.adjustSize()

        item.setSizeHint(label.sizeHint())
        self.log_list.addItem(item)
        self.log_list.setItemWidget(item, label)

        QTimer.singleShot(180_000, lambda: self._fade_and_remove_log_item(item, label))

    def switch_to_tab_from_text(self, text):
        match = re.search(r"[😴💶🛍️⚠️]\s+([A-Z0-9\-]+)", text)
        if not match:
            return
        tab_name = match.group(1).strip()
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i).strip().upper() == tab_name:
                self.tabs.setCurrentIndex(i)
                tab_bar = self.tabs.tabBar()
                original_color = tab_bar.tabTextColor(i)
                tab_bar.setTabTextColor(i, Qt.GlobalColor.magenta)
                QTimer.singleShot(1000, lambda: tab_bar.setTabTextColor(i, original_color))
                break


    def set_all_thresholds(self, value):
        for i in range(self.tabs.count()):
            self.tabs.widget(i).threshold_dropdown.setCurrentText(value)

    def set_all_delays(self, value):
        for i in range(self.tabs.count()):
            self.tabs.widget(i).delay_dropdown.setCurrentText(value)

    def init_controls(self):
        layout = QHBoxLayout()
        layout.setSpacing(12)

        self.load_btn = QPushButton("Load All")
        self.monitor_btn = QPushButton("Start Monitor All")

        # Threshold control
        self.global_threshold_dropdown = QComboBox()
        self.global_threshold_dropdown.addItems([str(i) for i in range(1, 11)])
        self.global_threshold_dropdown.setCurrentText("5")
        self.global_threshold_dropdown.currentTextChanged.connect(self.set_all_thresholds)

        threshold_box = QVBoxLayout()
        threshold_box.addWidget(QLabel("Max Order:"))
        threshold_box.addWidget(self.global_threshold_dropdown)
        threshold_widget = QWidget()
        threshold_widget.setLayout(threshold_box)

        # Delay control
        self.global_delay_dropdown = QComboBox()
        self.global_delay_dropdown.addItems([str(i) for i in range(1, 21)])
        self.global_delay_dropdown.setCurrentText("15")
        self.global_delay_dropdown.currentTextChanged.connect(self.set_all_delays)

        delay_box = QVBoxLayout()
        delay_box.addWidget(QLabel("Delay (min):"))
        delay_box.addWidget(self.global_delay_dropdown)
        delay_widget = QWidget()
        delay_widget.setLayout(delay_box)

        # Price control
        self.global_price_limit = QComboBox()
        self.global_price_limit.addItems([str(i) for i in range(10, 201, 5)])
        self.global_price_limit.setCurrentText("70")
        self.global_price_limit.currentTextChanged.connect(self.set_all_price_limits)

        price_box = QVBoxLayout()
        price_box.addWidget(QLabel("Limit Avg Price (€):"))
        price_box.addWidget(self.global_price_limit)
        price_widget = QWidget()
        price_widget.setLayout(price_box)

        # Final layout
        layout.addWidget(self.load_btn)
        layout.addWidget(self.monitor_btn)
        layout.addWidget(threshold_widget)
        layout.addWidget(delay_widget)
        layout.addWidget(price_widget)

        wrap = QWidget()
        wrap.setLayout(layout)
        self.setMenuWidget(wrap)

        self.load_btn.clicked.connect(self.load_all_tabs)
        self.monitor_btn.clicked.connect(self.toggle_all_monitoring)

    def add_tab(self, name="Tab", url="", threshold=5, resume_delay=1, max_order_price=100, from_config=False):
        tab = MonitorTab(self, name, url, threshold, resume_delay, max_order_price)
        index = self.tabs.addTab(tab, tab.tab_name)
        self.tabs.setCurrentIndex(index)
        if not from_config:
            tab.threshold_dropdown.setCurrentText(self.global_threshold_dropdown.currentText())
            tab.delay_dropdown.setCurrentText(self.global_delay_dropdown.currentText())
        else:
            tab.threshold_dropdown.setCurrentText(str(tab.threshold))
            tab.delay_dropdown.setCurrentText(str(tab.resume_delay))
        return tab

    def load_all_tabs(self):
        for i in range(self.tabs.count()):
            # use reload_page() so it applies the same date‑range injection and timer reset
            self.tabs.widget(i).reload_page()

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
        print("[DEBUG] Checking config file...")
        if not os.path.exists(CONFIG_FILE):
            print("[DEBUG] Config file not found.")
            self.add_tab(name="Tab 1")
            return

        try:
            with open(CONFIG_FILE, "r") as f:
                config_data = json.load(f)
            print(f"[DEBUG] Loaded config: {len(config_data)} tabs")
        except json.JSONDecodeError as e:
            print(f"[ERR] JSON decode error: {e}")
            self.add_tab(name="Tab 1")
            return
        except Exception as e:
            print(f"[ERR] Unexpected config error: {e}")
            self.add_tab(name="Tab 1")
            return

        for i, data in enumerate(config_data):
            try:
                filtered_data = {
                    "name": data.get("name", f"Tab {i+1}"),
                    "url": data.get("url", ""),
                    "threshold": int(data.get("threshold", 5)),
                    "resume_delay": int(data.get("resume_delay", 1)),
                    "max_order_price": float(data.get("max_order_price", 100))
                }
                print(f"[DEBUG] Adding tab: {filtered_data['name']} | Threshold: {filtered_data['threshold']} | Price Limit: {filtered_data['max_order_price']}")
                tab = self.add_tab(**filtered_data, from_config=True)
                tab.load_url(use_original_url=True)
            except Exception as e:
                print(f"[ERR] Failed to load tab {i+1}: {e}")

    def set_all_price_limits(self, value):
        for i in range(self.tabs.count()):
            self.tabs.widget(i).max_order_price = float(value)

    def closeEvent(self, event):
        with open(CONFIG_FILE, "w") as f:
            json.dump([self.tabs.widget(i).get_state() for i in range(self.tabs.count())], f)
        event.accept()
    
        
    def _fade_and_remove_log_item(self, item):
        effect = QGraphicsOpacityEffect()
        label.setGraphicsEffect(effect)

        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(1000)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)

        def on_finished():
            row = self.log_list.row(item)
            if row != -1:
                self.log_list.takeItem(row)

        animation.finished.connect(on_finished)
        animation.start()
    



if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    win = MainApp()
    # Optional patch loader
    try:
        
        import patches
        print("[MAIN] Connecting patch manually")
        patches.patch(win)
    except Exception as e:
        print("[WARN] No patch or patch error:", e)
    
    # ✅ Redirect after patch
    sys.stdout = sys.stderr = open(get_resource_path("monitor.log"), "a", buffering=1)
    win.show()
    win.log_event("🛍️ KRS has 3 order(s)\n                 🕛 Suggested offline: 00:30")
    exit_code = app.exec()
    os._exit(exit_code)  # Force exit, closes console even if opened via terminal
