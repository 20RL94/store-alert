# clickable_label.py
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import pyqtSignal

class ClickableLabel(QLabel):
    doubleClicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
