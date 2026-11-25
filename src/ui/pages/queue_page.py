"""The Queue page: every DownloadTask with live progress, color-coded
status, and per-row controls (cancel, retry, open folder, remove)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from download.manager import DownloadManager
from download.task import DownloadStatus, DownloadTask
from ui.theme import current_tokens
from ui.widgets.common import EmptyState, PageHeader, make_button, make_label

_COLUMNS = ["Title", "Status", "Progress", "Speed", "ETA", "Actions"]
ROW_HEIGHT = 48


def _format_speed(bps: float | None) -> str:
    if not bps:
        return ""
    for unit in ("B/s", "KB/s", "MB/s"):
        if bps < 1024:
            return f"{bps:.0f} {unit}"
        bps /= 1024
    return f"{bps:.1f} GB/s"


def _format_eta(seconds: int | None) -> str:
    if seconds is None:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


def _status_color(status: DownloadStatus) -> QColor:
    t = current_tokens()
    if status == DownloadStatus.COMPLETED:
        return QColor(t["success"])
    if status == DownloadStatus.FAILED:
        return QColor(t["danger"])
    if status in (DownloadStatus.DOWNLOADING, DownloadStatus.POST_PROCESSING):
        return QColor(t["accent"])
    return QColor(t["muted"])


class QueuePage(QWidget):
    active_count_changed = Signal(int)
    browse_requested = Signal()

    def __init__(self, manager: DownloadManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._row_by_task_id: dict[str, int] = {}
        self._status_by_task_id: dict[str, DownloadStatus] = {}

        self._build_ui()

        self._manager.task_added.connect(self._on_task_added)
        self._manager.task_updated.connect(self._on_task_updated)
        self._manager.task_removed.connect(self._on_task_removed)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header = PageHeader("Queue", "")
        self.summary_label = make_label("No downloads yet", "pageSubtitle")
        header.layout().itemAt(0).layout().addWidget(self.summary_label)
        self.clear_completed_button = make_button("Clear finished", icon="check", tooltip="Remove finished downloads from the list")
        self.clear_completed_button.clicked.connect(self._manager.clear_completed)
        header.actions.addWidget(self.clear_completed_button)
        layout.addWidget(header)

        self.stack = QStackedWidget()
        self.empty_state = EmptyState(
            "queue",
            "Nothing in the queue",
            "Links you send to download show up here with live progress.",
            action_text="Add a download",
        )
        self.empty_state.action_button.clicked.connect(self.browse_requested.emit)
        self.stack.addWidget(self.empty_state)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        header_view = self.table.horizontalHeader()
        header_view.setHighlightSections(False)
        header_view.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.Interactive)
        header_view.setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 84)
        self.table.setColumnWidth(4, 56)
        # Actions holds up to 3 icon buttons; size it to its content.
        header_view.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.stack.addWidget(self.table)
        layout.addWidget(self.stack, stretch=1)
        self._refresh_summary()

    # ---------------------------------------------------------------- rows

    def _on_task_added(self, task: DownloadTask) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._row_by_task_id[task.id] = row
        self._status_by_task_id[task.id] = task.status

        title_item = QTableWidgetItem(task.display_title)
        title_item.setToolTip(task.url)
        self.table.setItem(row, 0, title_item)
        status_item = QTableWidgetItem(task.status.display_label)
        status_item.setForeground(_status_color(task.status))
        self.table.setItem(row, 1, status_item)

        self.table.setCellWidget(row, 2, self._build_progress_cell())

        self.table.setItem(row, 3, QTableWidgetItem(""))
        self.table.setItem(row, 4, QTableWidgetItem(""))
        self.table.setCellWidget(row, 5, self._build_actions_widget(task))
        self._refresh_summary()

    def _build_progress_cell(self) -> QProgressBar:
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        # Slim bar, vertically centred in the row by its QSS margin; the
        # percentage is shown in the Status column instead.
        progress_bar.setTextVisible(False)
        progress_bar.setObjectName("rowProgress")
        return progress_bar

    def _on_task_updated(self, task: DownloadTask) -> None:
        row = self._row_by_task_id.get(task.id)
        if row is None:
            return
        self._status_by_task_id[task.id] = task.status

        self.table.item(row, 0).setText(task.display_title)
        status_text = task.status.display_label
        status_item = self.table.item(row, 1)
        percent = task.progress.percent if task.progress is not None else None
        if task.status == DownloadStatus.DOWNLOADING and percent is not None:
            status_text = f"Downloading · {int(percent)}%"
        if task.status == DownloadStatus.FAILED and task.error_message:
            status_text = f"Failed: {task.error_message}"
            status_item.setToolTip(task.error_message)
        elif task.status == DownloadStatus.FAILED:
            status_item.setToolTip("")
        status_item.setText(status_text)
        status_item.setForeground(_status_color(task.status))

        progress_bar = self.table.cellWidget(row, 2)
        if isinstance(progress_bar, QProgressBar):
            if task.progress is not None and task.progress.percent is not None:
                progress_bar.setValue(int(task.progress.percent))
            if task.status == DownloadStatus.COMPLETED:
                progress_bar.setValue(100)
            state = {DownloadStatus.COMPLETED: "done", DownloadStatus.FAILED: "failed"}.get(task.status, "")
            if progress_bar.property("state") != state:
                progress_bar.setProperty("state", state)
                progress_bar.style().unpolish(progress_bar)
                progress_bar.style().polish(progress_bar)

        if task.progress is not None:
            self.table.item(row, 3).setText(_format_speed(task.progress.speed_bps))
            self.table.item(row, 4).setText(_format_eta(task.progress.eta_seconds))
        if task.is_finished:
            self.table.item(row, 3).setText("")
            self.table.item(row, 4).setText("")

        self._refresh_actions_widget(task)
        self._refresh_summary()

    def _on_task_removed(self, task_id: str) -> None:
        self._status_by_task_id.pop(task_id, None)
        row = self._row_by_task_id.pop(task_id, None)
        if row is None:
            return
        self.table.removeRow(row)
        for tid, r in list(self._row_by_task_id.items()):
            if r > row:
                self._row_by_task_id[tid] = r - 1
        self._refresh_summary()

    def _build_actions_widget(self, task: DownloadTask) -> QWidget:
        task_id = task.id
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 8, 0)
        layout.setSpacing(2)

        cancel_button = make_button(variant="icon", icon="close", tooltip="Cancel download")
        cancel_button.setObjectName("cancel_button")
        cancel_button.clicked.connect(lambda: self._manager.cancel(task_id))

        retry_button = make_button(variant="icon", icon="retry", tooltip="Retry")
        retry_button.setObjectName("retry_button")
        retry_button.setVisible(False)
        retry_button.clicked.connect(lambda: self._manager.retry(task_id))

        open_folder_button = make_button(variant="icon", icon="folder", tooltip="Show in folder")
        open_folder_button.setObjectName("open_folder_button")
        open_folder_button.setVisible(False)
        open_folder_button.clicked.connect(lambda: self._open_folder(task_id))

        remove_button = make_button(variant="icon", icon="trash", tooltip="Remove from list")
        remove_button.setObjectName("remove_button")
        remove_button.clicked.connect(lambda: self._manager.remove(task_id))

        for button in (cancel_button, retry_button, open_folder_button, remove_button):
            layout.addWidget(button)
        return container

    def _refresh_actions_widget(self, task: DownloadTask) -> None:
        row = self._row_by_task_id.get(task.id)
        if row is None:
            return
        container = self.table.cellWidget(row, 5)
        if container is None:
            return
        cancel_button = container.findChild(QPushButton, "cancel_button")
        retry_button = container.findChild(QPushButton, "retry_button")
        open_folder_button = container.findChild(QPushButton, "open_folder_button")
        if cancel_button is not None:
            cancel_button.setVisible(not task.is_finished)
        if retry_button is not None:
            retry_button.setVisible(task.can_retry)
        if open_folder_button is not None:
            open_folder_button.setVisible(task.status == DownloadStatus.COMPLETED)
            open_folder_button.setProperty("taskFolder", self._folder_for(task))

    @staticmethod
    def _folder_for(task: DownloadTask) -> str:
        if task.destination_path:
            return str(Path(task.destination_path).parent)
        return task.output_dir

    def _open_folder(self, task_id: str) -> None:
        row = self._row_by_task_id.get(task_id)
        container = self.table.cellWidget(row, 5) if row is not None else None
        button = container.findChild(QPushButton, "open_folder_button") if container else None
        folder = button.property("taskFolder") if button is not None else None
        if folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ------------------------------------------------------------- summary

    def active_count(self) -> int:
        finished = (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED)
        return sum(1 for s in self._status_by_task_id.values() if s not in finished)

    def _refresh_summary(self) -> None:
        statuses = list(self._status_by_task_id.values())
        self.stack.setCurrentWidget(self.table if statuses else self.empty_state)
        active = self.active_count()
        done = statuses.count(DownloadStatus.COMPLETED)
        failed = statuses.count(DownloadStatus.FAILED)
        if not statuses:
            text = "No downloads yet"
        else:
            parts = [f"{active} in progress" if active else "All done"]
            if done:
                parts.append(f"{done} completed")
            if failed:
                parts.append(f"{failed} failed")
            text = "  ·  ".join(parts)
        self.summary_label.setText(text)
        self.clear_completed_button.setEnabled(len(statuses) > active)
        self.active_count_changed.emit(active)
