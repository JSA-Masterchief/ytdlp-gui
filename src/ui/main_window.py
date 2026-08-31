"""Main application window: header, sidebar navigation, and page stack.

This is intentionally minimal for Phase 1 — a real shell that runs, with a
sidebar and an empty-state page stack. Real pages (Download, Queue, History,
Settings, Logs) are added in later phases without needing to restructure
this file.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.constants import APP_NAME, APP_VERSION

NAV_SECTIONS = ["Download", "Queue", "History", "Formats", "Settings", "Logs"]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1100, 720)

        self._build_header()
        self._build_body()

    def _build_header(self) -> None:
        toolbar = QToolBar("Header")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        title = QLabel(f"  {APP_NAME}")
        title.setStyleSheet("font-weight: 600; font-size: 14px;")
        toolbar.addWidget(title)

    def _build_body(self) -> None:
        splitter = QSplitter(Qt.Horizontal)

        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(180)
        for section in NAV_SECTIONS:
            QListWidgetItem(section, self.nav_list)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)

        self.page_stack = QStackedWidget()
        for section in NAV_SECTIONS:
            self.page_stack.addWidget(self._placeholder_page(section))

        splitter.addWidget(self.nav_list)
        splitter.addWidget(self.page_stack)
        splitter.setStretchFactor(1, 1)

        self.nav_list.setCurrentRow(0)
        self.setCentralWidget(splitter)

    def _placeholder_page(self, name: str) -> QWidget:
        # Replaced by real page widgets (ui/pages/*) in later phases.
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel(f"{name} page — coming soon")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: gray; font-size: 16px;")
        layout.addWidget(label)
        return widget

    def _on_nav_changed(self, index: int) -> None:
        if index >= 0:
            self.page_stack.setCurrentIndex(index)
