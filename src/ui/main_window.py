"""Main application window: header, sidebar navigation, and page stack."""

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

from app.config import load_config
from app.constants import APP_NAME, APP_VERSION
from backend.ytdlp_backend import YtdlpBackend
from download.history import HistoryStore
from download.manager import DownloadManager
from services.history_recorder import HistoryRecorder
from ui.pages.download_page import DownloadPage
from ui.pages.history_page import HistoryPage
from ui.pages.logs_page import LogsPage
from ui.pages.queue_page import QueuePage
from ui.pages.settings_page import SettingsPage
from utils.paths import get_history_file_path, get_log_file_path

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

        self.config = load_config()
        self.download_manager = DownloadManager(YtdlpBackend(), max_concurrent=self.config.max_concurrent_downloads)
        self.history_store = HistoryStore(get_history_file_path())
        # Kept as a real attribute (not a throwaway expression): a
        # QObject connected to a signal still needs a live Python
        # reference somewhere, or it can be garbage collected and
        # silently stop recording — see services/history_recorder.py.
        self.history_recorder = HistoryRecorder(self.download_manager, self.history_store, parent=self)

        self.download_page = DownloadPage(
            download_manager=self.download_manager,
            initial_output_dir=self.config.download_directory,
            initial_filename_template=self.config.filename_template,
        )
        self.history_page = HistoryPage(self.history_store)
        self.history_page.redownload_requested.connect(self._on_redownload_requested)
        self.settings_page = SettingsPage(self.config)
        self.settings_page.settings_saved.connect(self._on_settings_saved)

        self.page_stack = QStackedWidget()
        for section in NAV_SECTIONS:
            if section == "Download":
                self.page_stack.addWidget(self.download_page)
            elif section == "Queue":
                self.page_stack.addWidget(QueuePage(self.download_manager))
            elif section == "History":
                self.page_stack.addWidget(self.history_page)
            elif section == "Settings":
                self.page_stack.addWidget(self.settings_page)
            elif section == "Logs":
                self.page_stack.addWidget(LogsPage(get_log_file_path()))
            else:
                self.page_stack.addWidget(self._placeholder_page(section))

        splitter.addWidget(self.nav_list)
        splitter.addWidget(self.page_stack)
        splitter.setStretchFactor(1, 1)

        self.nav_list.setCurrentRow(0)
        self.setCentralWidget(splitter)

    def _placeholder_page(self, name: str) -> QWidget:
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

    def _on_redownload_requested(self, url: str) -> None:
        self.download_page.set_url(url)
        self.nav_list.setCurrentRow(NAV_SECTIONS.index("Download"))

    def _on_settings_saved(self, new_config) -> None:  # noqa: ANN001
        self.config = new_config
        self.download_manager.set_max_concurrent(new_config.max_concurrent_downloads)
        self.download_page.apply_settings(new_config.download_directory, new_config.filename_template)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.download_manager.shutdown()
        super().closeEvent(event)
