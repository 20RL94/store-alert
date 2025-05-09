#patches.py
from datetime import datetime
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QListWidgetItem
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
        label.doubleClicked.connect(lambda it=item: on_label_clicked(it))
        item.setSizeHint(label.sizeHint())
        main_window.log_list.setItemWidget(item, label)

    print("[PATCH] Clickable log labels enabled.")

    def patched_fade_and_remove_log_item(item):
        widget = main_window.log_list.itemWidget(item)
        if not widget:
            return

        effect = QGraphicsOpacityEffect()
        widget.setGraphicsEffect(effect)

        animation = QPropertyAnimation(effect, b"opacity", main_window)
        animation.setDuration(1000)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)

        def on_finished():
            row = main_window.log_list.row(item)
            if row != -1:
                main_window.log_list.takeItem(row)
            widget.deleteLater()

        animation.finished.connect(on_finished)
        animation.start()

    # 🔁 Replace the original method
    main_window._fade_and_remove_log_item = patched_fade_and_remove_log_item
    print("[PATCH] Custom fade-and-remove applied.")

    from clickable_label import ClickableLabel
    def patched_log_event(message):
        ts = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem()
        label_text = f"{ts} {message}"
        item.setData(Qt.ItemDataRole.UserRole, label_text)

        label = ClickableLabel(label_text)
        label.setWordWrap(True)
        label.setContentsMargins(6, 6, 6, 6)
        label.setStyleSheet("font-size: 12px;")
        label.adjustSize()
        label.doubleClicked.connect(lambda it=item: on_label_clicked(it))

        item.setSizeHint(label.sizeHint())
        main_window.log_list.addItem(item)
        main_window.log_list.setItemWidget(item, label)

        QTimer.singleShot(180_000, lambda: main_window._fade_and_remove_log_item(item))

# 🔁 Replace the original log_event method
    main_window.log_event = patched_log_event
    print("[PATCH] log_event override complete.")
