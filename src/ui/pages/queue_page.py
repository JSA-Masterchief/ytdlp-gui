"""The Queue page: shows every DownloadTask with live progress and the
per-row controls from the spec (cancel, retry, remove, clear completed).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from download.manager import DownloadManager
from download.task import DownloadStatus, DownloadTask

_COLUMNS = ["Title", "Status", "Progress", "Speed", "ETA", "Actions"]


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


class QueuePage(QWidget):
    def __init__(self, manager: DownloadManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._row_by_task_id: dict[str, int] = {}

        self._build_ui()

        self._manager.task_added.connect(self._on_task_added)
        self._manager.task_updated.connect(self._on_task_updated)
        self._manager.task_removed.connect(self._on_task_removed)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.clear_completed_button = QPushButton("Clear completed")
        self.clear_completed_button.clicked.connect(self._manager.clear_completed)
        toolbar.addWidget(self.clear_completed_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    # -- manager signal handlers ---------------------------------------------

    def _on_task_added(self, task: DownloadTask) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._row_by_task_id[task.id] = row

        self.table.setItem(row, 0, QTableWidgetItem(task.display_title))
        self.table.setItem(row, 1, QTableWidgetItem(task.status.display_label))

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        self.table.setCellWidget(row, 2, progress_bar)

        self.table.setItem(row, 3, QTableWidgetItem(""))
        self.table.setItem(row, 4, QTableWidgetItem(""))
        self.table.setCellWidget(row, 5, self._build_actions_widget(task.id))

    def _on_task_updated(self, task: DownloadTask) -> None:
        row = self._row_by_task_id.get(task.id)
        if row is None:
            return

        self.table.item(row, 0).setText(task.display_title)
        status_text = task.status.display_label
        if task.status == DownloadStatus.FAILED and task.error_message:
            status_text = f"Failed: {task.error_message}"
        self.table.item(row, 1).setText(status_text)

        progress_bar = self.table.cellWidget(row, 2)
        if isinstance(progress_bar, QProgressBar) and task.progress is not None:
            if task.progress.percent is not None:
                progress_bar.setValue(int(task.progress.percent))
            elif task.status == DownloadStatus.COMPLETED:
                progress_bar.setValue(100)

        if task.progress is not None:
            self.table.item(row, 3).setText(_format_speed(task.progress.speed_bps))
            self.table.item(row, 4).setText(_format_eta(task.progress.eta_seconds))

        self._refresh_actions_widget(task)

    def _on_task_removed(self, task_id: str) -> None:
        row = self._row_by_task_id.pop(task_id, None)
        if row is None:
            return
        self.table.removeRow(row)
        for tid, r in list(self._row_by_task_id.items()):
            if r > row:
                self._row_by_task_id[tid] = r - 1

    # -- per-row action buttons -----------------------------------------------

    def _build_actions_widget(self, task_id: str) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("cancel_button")
        cancel_button.clicked.connect(lambda: self._manager.cancel(task_id))

        retry_button = QPushButton("Retry")
        retry_button.setObjectName("retry_button")
        retry_button.setVisible(False)
        retry_button.clicked.connect(lambda: self._manager.retry(task_id))

        remove_button = QPushButton("Remove")
        remove_button.setObjectName("remove_button")
        remove_button.clicked.connect(lambda: self._manager.remove(task_id))

        layout.addWidget(cancel_button)
        layout.addWidget(retry_button)
        layout.addWidget(remove_button)
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
        if cancel_button is not None:
            cancel_button.setVisible(not task.is_finished)
        if retry_button is not None:
            retry_button.setVisible(task.can_retry)
