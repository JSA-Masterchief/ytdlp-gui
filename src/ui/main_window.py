"""Main application window: a sidebar (brand, navigation with a live queue
badge, theme and About) beside the page stack."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QProcess, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from app.config import load_config, save_config
from app.constants import APP_NAME, APP_VERSION
from backend.ffmpeg_manager import resolve_ffmpeg_location
from backend.ytdlp_backend import YtdlpBackend
from download.history import HistoryStore
from download.manager import DownloadManager
from download.task import DownloadStatus
from services.history_recorder import HistoryRecorder
from services.ytdlp_update_service import YtdlpUpdateService
from ui.icons import make_icon, set_button_icon
from ui.pages.download_page import DownloadPage
from ui.pages.history_page import HistoryPage
from ui.pages.logs_page import LogsPage
from ui.pages.queue_page import QueuePage
from ui.pages.settings_page import SettingsPage
from ui.theme import apply_theme, current_tokens, next_theme
from ui.widgets.common import Toast, make_button
from utils.paths import get_history_file_path, get_log_file_path, get_resource_path, get_window_state_path


NAV_SECTIONS = ["Download", "Queue", "History", "Settings", "Logs"]


_NAV_ICONS = {"Download": "download", "Queue": "queue", "History": "history", "Settings": "settings", "Logs": "logs"}
_THEME_ICONS = {"system": "system", "light": "sun", "dark": "moon"}

# Opening size scales with the screen (a share of it, never filling it),
# clamped to sensible bounds; after that the window remembers its own size.


DEFAULT_SCREEN_SHARE = (0.66, 0.80)
DEFAULT_WINDOW_SIZE = (1180, 820)  # upper bound for the opening size
MINIMUM_WINDOW_SIZE = (640, 480)
COMPACT_SIDEBAR_BELOW = 820  # window width under which the sidebar shows icons only
SIDEBAR_WIDTH = 200
SIDEBAR_WIDTH_COMPACT = 64


_NAME_ROLE = Qt.UserRole
_BADGE_ROLE = Qt.UserRole + 1


_ABOUT_TEXT = (
    f"<b>{APP_NAME}</b> v{APP_VERSION}<br><br>"
    "A desktop frontend for yt-dlp.<br><br>"
    "This application does not implement or facilitate DRM circumvention. "
    "You are responsible for ensuring your use complies with applicable laws, "
    "the terms of service of the sites you download from, and the rights "
    "holders of any content."
)


class _NavDelegate(QStyledItemDelegate):
    """Draws the normal nav item plus a count badge (e.g. active downloads)."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._window = window

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: ANN001
        super().paint(painter, option, index)
        count = index.data(_BADGE_ROLE) or 0
        if not count:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        tokens = current_tokens()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(tokens["accent"]))
        rect: QRect = option.rect.adjusted(8, 2, -8, -2)  # matches the item's QSS margins
        if self._window.is_sidebar_compact():
            painter.drawEllipse(QRectF(rect.right() - 16, rect.top() + 6, 9, 9))
        else:
            text = str(count) if count < 100 else "99+"
            font = QFont(option.font)
            font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
            font.setBold(True)
            painter.setFont(font)
            width = max(20, painter.fontMetrics().horizontalAdvance(text) + 12)
            pill = QRectF(rect.right() - width - 8, rect.center().y() - 9, width, 18)
            painter.drawRoundedRect(pill, 9, 9)
            painter.setPen(QColor("white"))
            painter.drawText(pill, Qt.AlignCenter, text)
        painter.restore()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self._window_state_path = get_window_state_path()
        self._compact = False
        self._notified_task_ids: set[str] = set()

        self.config = load_config()
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self.config.theme)

        self._build_body()
        self._apply_initial_geometry()
        self._bind_shortcuts()

    # -------------------------------------------------------------- layout

    def _apply_initial_geometry(self) -> None:
        self.setMinimumSize(*MINIMUM_WINDOW_SIZE)
        if self._restore_saved_geometry():
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(*DEFAULT_WINDOW_SIZE)
            return
        available = screen.availableGeometry()
        width, height = default_window_size(available.width(), available.height())
        self.resize(width, height)
        self.move(
            available.x() + (available.width() - width) // 2,
            available.y() + (available.height() - height) // 2,
        )

    def _restore_saved_geometry(self) -> bool:
        try:
            data = Path(self._window_state_path).read_bytes()
        except OSError:
            return False
        if not data or not self.restoreGeometry(QByteArray(data)):
            return False
        # Never come back larger than the current screen (e.g. after moving
        # from a big monitor to a laptop).
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            if self.width() > available.width() or self.height() > available.height():
                self.resize(*default_window_size(available.width(), available.height()))
        return True

    def _save_geometry(self) -> None:
        try:
            Path(self._window_state_path).write_bytes(bytes(self.saveGeometry()))
        except OSError:
            pass

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 16, 0, 12)
        layout.setSpacing(4)

        brand = QHBoxLayout()
        brand.setContentsMargins(16, 0, 12, 12)
        brand.setSpacing(10)
        self.brand_icon = QLabel()
        icon_path = get_resource_path("assets/icon.ico")
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            self.brand_icon.setPixmap(pixmap.scaled(QSize(30, 30), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand.addWidget(self.brand_icon)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        title = QLabel(APP_NAME)
        title.setObjectName("brandTitle")
        title.setAccessibleName("Application title")
        subtitle = QLabel(f"v{APP_VERSION}")
        subtitle.setObjectName("brandSubtitle")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        self.brand_text = QWidget()
        self.brand_text.setLayout(brand_text)
        brand.addWidget(self.brand_text, stretch=1)
        layout.addLayout(brand)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navList")
        self.nav_list.setAccessibleName("Main navigation")
        self.nav_list.setIconSize(QSize(18, 18))
        self.nav_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_list.setItemDelegate(_NavDelegate(self))
        for index, section in enumerate(NAV_SECTIONS, start=1):
            item = QListWidgetItem(section, self.nav_list)
            item.setData(_NAME_ROLE, section)
            item.setToolTip(f"{section}  (Ctrl+{index})")
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        layout.addWidget(self.nav_list, stretch=1)

        self.theme_toggle_button = make_button(variant="ghost")
        self.theme_toggle_button.setAccessibleName("Toggle theme")
        self.theme_toggle_button.setToolTip("Switch between System, Light and Dark")
        self.theme_toggle_button.clicked.connect(self._on_theme_toggle_clicked)
        self.about_button = make_button("About", variant="ghost", icon="info")
        self.about_button.setAccessibleName("About this application")
        self.about_button.clicked.connect(self._on_about_clicked)
        for button in (self.theme_toggle_button, self.about_button):
            set_button_icon(button, button.property("iconName") or "info", role="muted")
            layout.addWidget(button)
        self._sidebar_buttons = layout
        self._update_theme_toggle_label()
        return sidebar

    def _build_body(self) -> None:
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = self._build_sidebar()
        body_layout.addWidget(self.sidebar)

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
            ffmpeg_location=resolve_ffmpeg_location(self.config.ffmpeg_path),
        )
        self.download_page.view_queue_requested.connect(lambda: self.go_to("Queue"))
        self.download_page.output_dir_changed.connect(self._on_output_dir_changed)
        self.queue_page = QueuePage(self.download_manager)
        self.queue_page.active_count_changed.connect(self._on_active_count_changed)
        self.queue_page.browse_requested.connect(lambda: self.go_to("Download"))
        self.history_page = HistoryPage(self.history_store)
        self.history_page.redownload_requested.connect(self._on_redownload_requested)
        self.update_service = YtdlpUpdateService(self)
        self.update_service.check_finished.connect(self._on_quiet_check_finished)
        self.update_service.install_finished.connect(self._on_update_installed)
        self._quiet_check_pending = False
        self.settings_page = SettingsPage(self.config, update_service=self.update_service)
        self.settings_page.settings_saved.connect(self._on_settings_saved)
        self.settings_page.restart_requested.connect(self.restart_app)
        self.logs_page = LogsPage(get_log_file_path())

        pages = {
            "Download": self.download_page,
            "Queue": self.queue_page,
            "History": self.history_page,
            "Settings": self.settings_page,
            "Logs": self.logs_page,
        }
        self.page_stack = QStackedWidget()
        for section in NAV_SECTIONS:
            self.page_stack.addWidget(pages[section])
        body_layout.addWidget(self.page_stack, stretch=1)

        self.download_manager.task_updated.connect(self._on_task_updated)

        self.nav_list.setCurrentRow(0)
        self.setCentralWidget(body)
        self.toast = Toast(body)
        self._refresh_nav_icons()

    def _bind_shortcuts(self) -> None:
        self._shortcuts = []
        for index, section in enumerate(NAV_SECTIONS, start=1):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
            shortcut.activated.connect(lambda s=section: self.go_to(s))
            self._shortcuts.append(shortcut)

    # ------------------------------------------------------------ helpers

    def go_to(self, section: str) -> None:
        self.nav_list.setCurrentRow(NAV_SECTIONS.index(section))

    def is_sidebar_compact(self) -> bool:
        return self._compact

    def _refresh_nav_icons(self) -> None:
        tokens = current_tokens()
        for row in range(self.nav_list.count()):
            item = self.nav_list.item(row)
            name = item.data(_NAME_ROLE)
            icon = make_icon(_NAV_ICONS[name], QColor(tokens["text"]))
            selected = make_icon(_NAV_ICONS[name], QColor(tokens["accent_soft_text"]))
            icon.addPixmap(selected.pixmap(48, 48), QIcon.Selected)
            item.setIcon(icon)

    def _update_theme_toggle_label(self) -> None:
        theme = self.config.theme
        self._theme_label = f"Theme: {theme.capitalize()}"
        set_button_icon(self.theme_toggle_button, _THEME_ICONS.get(theme, "system"), role="muted")
        self.theme_toggle_button.setText("" if self._compact else self._theme_label)
        self.theme_toggle_button.setToolTip(f"{self._theme_label} — click to switch")

    def _set_compact(self, compact: bool) -> None:
        if compact == self._compact:
            return
        self._compact = compact
        self.sidebar.setFixedWidth(SIDEBAR_WIDTH_COMPACT if compact else SIDEBAR_WIDTH)
        self.brand_text.setVisible(not compact)
        for row in range(self.nav_list.count()):
            item = self.nav_list.item(row)
            item.setText("" if compact else item.data(_NAME_ROLE))
        self.about_button.setText("" if compact else "About")
        self._update_theme_toggle_label()
        self.nav_list.viewport().update()

    def resizeEvent(self, event) -> None:  # noqa: N802, ANN001
        super().resizeEvent(event)
        self._set_compact(self.width() < COMPACT_SIDEBAR_BELOW)
        if hasattr(self, "toast"):
            self.toast.reposition()

    # ------------------------------------------------------------ events

    def _on_theme_toggle_clicked(self) -> None:
        new_theme = next_theme(self.config.theme)
        self.config.theme = new_theme
        save_config(self.config)
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, new_theme)
        self._refresh_nav_icons()
        self._update_theme_toggle_label()
        if hasattr(self, "settings_page"):
            idx = self.settings_page.theme_combo.findData(new_theme)
            if idx >= 0:
                self.settings_page.theme_combo.setCurrentIndex(idx)

    def _on_about_clicked(self) -> None:
        QMessageBox.about(self, f"About {APP_NAME}", _ABOUT_TEXT)

    def _on_nav_changed(self, index: int) -> None:
        if index >= 0:
            self.page_stack.setCurrentIndex(index)
            if NAV_SECTIONS[index] == "Logs":
                self.logs_page.refresh()

    def _on_active_count_changed(self, count: int) -> None:
        item = self.nav_list.item(NAV_SECTIONS.index("Queue"))
        item.setData(_BADGE_ROLE, count)
        self.setWindowTitle(f"{APP_NAME} — {count} downloading" if count else APP_NAME)

    def _on_task_updated(self, task) -> None:  # noqa: ANN001
        if task.id in self._notified_task_ids or not task.is_finished:
            return
        if task.status == DownloadStatus.COMPLETED:
            self._notified_task_ids.add(task.id)
            folder = str(Path(task.destination_path).parent) if task.destination_path else task.output_dir
            self.toast.show_message(
                f"Downloaded: {task.display_title}",
                "Show in folder",
                lambda f=folder: self._open_folder(f),
            )
        elif task.status == DownloadStatus.FAILED:
            self._notified_task_ids.add(task.id)
            self.toast.show_message(f"Download failed: {task.display_title}", "View", lambda: self.go_to("Queue"))

    @staticmethod
    def _open_folder(folder: str) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ------------------------------------------------------ yt-dlp updates

    def check_for_ytdlp_update_quietly(self) -> None:
        """Startup check: only speaks up if there is something to install."""
        self._quiet_check_pending = self.update_service.check()

    def _on_quiet_check_finished(self, release, _running: str) -> None:  # noqa: ANN001
        if not self._quiet_check_pending:
            return
        self._quiet_check_pending = False
        if release is None:
            return
        self.toast.show_message(
            f"yt-dlp {release.version} is available with the latest site fixes.",
            "Update",
            lambda r=release: self._install_update(r),
            duration_ms=10_000,
        )

    def _install_update(self, release) -> None:  # noqa: ANN001
        self.settings_page.show_available_update(release)
        self.settings_page._on_install_update()
        self.toast.show_message(f"Downloading yt-dlp {release.version}…", duration_ms=3000)

    def _on_update_installed(self, version: str) -> None:
        self.toast.show_message(
            f"yt-dlp {version} is ready. Restart to start using it.",
            "Restart",
            self.restart_app,
            duration_ms=10_000,
        )

    def restart_app(self) -> None:
        active = self.queue_page.active_count()
        if active:
            answer = QMessageBox.question(
                self,
                "Restart now?",
                f"{active} download(s) are still running. Restarting stops them "
                "(you can retry them afterwards). Restart anyway?",
            )
            if answer != QMessageBox.Yes:
                return
        if getattr(sys, "frozen", False):
            program, args = sys.executable, sys.argv[1:]
        else:
            program, args = sys.executable, sys.argv
        QProcess.startDetached(program, args)
        self.close()

    def _on_output_dir_changed(self, directory: str) -> None:
        self.config.download_directory = directory
        save_config(self.config)
        self.settings_page.download_dir_edit.setText(directory)

    def _on_redownload_requested(self, url: str) -> None:
        self.download_page.set_url(url)
        self.go_to("Download")

    def _on_settings_saved(self, new_config) -> None:  # noqa: ANN001
        theme_changed = new_config.theme != self.config.theme
        self.config = new_config
        self.download_manager.set_max_concurrent(new_config.max_concurrent_downloads)
        self.download_page.apply_settings(
            new_config.download_directory,
            new_config.filename_template,
            resolve_ffmpeg_location(new_config.ffmpeg_path),
        )

        if theme_changed:
            app = QApplication.instance()
            if app is not None:
                apply_theme(app, new_config.theme)
            self._refresh_nav_icons()
            self._update_theme_toggle_label()
        self.toast.show_message("Settings saved", duration_ms=2000)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_geometry()
        self.download_manager.shutdown()
        super().closeEvent(event)


def default_window_size(available_width: int, available_height: int) -> tuple[int, int]:
    """Opening size for a screen: a comfortable share of it, clamped between
    the minimum and DEFAULT_WINDOW_SIZE, and never larger than the screen."""
    width = int(available_width * DEFAULT_SCREEN_SHARE[0])
    height = int(available_height * DEFAULT_SCREEN_SHARE[1])
    width = min(DEFAULT_WINDOW_SIZE[0], max(880, width))
    height = min(DEFAULT_WINDOW_SIZE[1], max(560, height))
    width = min(width, int(available_width * 0.94))
    height = min(height, int(available_height * 0.92))
    return max(MINIMUM_WINDOW_SIZE[0], width), max(MINIMUM_WINDOW_SIZE[1], height)
