from PyQt6.QtCore import Qt, QTimer
import re

def patch(main_window):
    print("✔ Patch loaded")

    def on_label_clicked(item):
        print("[PATCH] Label clicked.")
        text = item.data(Qt.ItemDataRole.UserRole)
        print(f"[PATCH] Clicked text: {text}")
        if not text:
            return

        match = re.search(r"[😴💶🛍️⚠️]\s+([A-Z0-9\-]+)", text)
        if not match:
            return

        tab_name = match.group(1).strip()
        for i in range(main_window.tabs.count()):
            if main_window.tabs.tabText(i).strip().upper() == tab_name:
                main_window.tabs.setCurrentIndex(i)
                tab_bar = main_window.tabs.tabBar()
                original_color = tab_bar.tabTextColor(i)
                tab_bar.setTabTextColor(i, Qt.GlobalColor.magenta)
                QTimer.singleShot(1000, lambda: tab_bar.setTabTextColor(i, original_color))
                break

    # Patch the log_list to re-bind all labels as clickable
    from clickable_label import ClickableLabel
    for i in range(main_window.log_list.count()):
        item = main_window.log_list.item(i)
        label_text = item.data(Qt.ItemDataRole.UserRole)
        if not label_text:
            continue
        label = ClickableLabel(label_text)
        label.setWordWrap(True)
        label.setContentsMargins(6, 6, 6, 6)
        label.setStyleSheet("font-size: 12px;")
        label.adjustSize()
        label.clicked.connect(lambda _, it=item: on_label_clicked(it))
        item.setSizeHint(label.sizeHint())
        main_window.log_list.setItemWidget(item, label)

    print("[PATCH] Clickable log labels enabled.")
