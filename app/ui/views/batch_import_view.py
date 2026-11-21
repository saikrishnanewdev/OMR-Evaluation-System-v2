"""Batch import and processing view with QThread worker and real-time progress updates."""
from pathlib import Path
from typing import List, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QProgressBar, QTableWidget, QTableWidgetItem, QFileDialog,
    QMessageBox, QFrame, QHeaderView
)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont, QColor
from app.models.entities import Examination, AnswerKey
from app.database.repository import Repository, repository
from app.services.evaluation_service import EvaluationService, evaluation_service


class BatchWorker(QThread):
    """Background worker thread executing OMR evaluation across large file batches."""

    progress = Signal(int, int, str, str)  # (current, total, filename, status)
    finished = Signal(dict)

    def __init__(
        self,
        exam: Examination,
        answer_key: AnswerKey,
        file_paths: List[Path],
        service: EvaluationService = evaluation_service
    ):
        super().__init__()
        self.exam = exam
        self.answer_key = answer_key
        self.file_paths = file_paths
        self.service = service
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        total = len(self.file_paths)
        successful = 0
        review_required = 0
        failed = 0

        for idx, path in enumerate(self.file_paths, start=1):
            if self._is_cancelled:
                break

            filename = path.name
            try:
                sheet = self.service.process_single_sheet(self.exam, self.answer_key, path)
                if sheet.status == "SUCCESS":
                    successful += 1
                    status_str = "SUCCESS"
                elif sheet.status == "REVIEW_REQUIRED":
                    review_required += 1
                    status_str = "REVIEW_REQUIRED"
                else:
                    failed += 1
                    status_str = sheet.status

                self.progress.emit(idx, total, filename, status_str)
            except Exception as e:
                failed += 1
                self.progress.emit(idx, total, filename, f"FAILED: {e}")

        # Recalculate ranks across examination
        self.service.recalculate_exam_ranks(self.exam.id)

        self.finished.emit({
            "total": total,
            "successful": successful,
            "review_required": review_required,
            "failed": failed,
            "cancelled": self._is_cancelled
        })


class BatchImportView(QWidget):
    """View to manage scanning batch queues, start parallel execution, and monitor status."""

    batchCompleted = Signal()

    def __init__(self, repo: Repository = repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.current_exam: Optional[Examination] = None
        self.current_key: Optional[AnswerKey] = None
        self.queued_files: List[Path] = []
        self.worker: Optional[BatchWorker] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header Title
        title_label = QLabel("Batch OMR Ingestion & Automated Processing")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title_label.setStyleSheet("color: #FFFFFF;")
        layout.addWidget(title_label)

        # Action Buttons Toolbar
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        btn_style = """
            QPushButton {
                background-color: #0E639C;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: 500;
            }
            QPushButton:hover { background-color: #1177BB; }
            QPushButton:disabled { background-color: #3E3E42; color: #888888; }
        """

        self.btn_add_files = QPushButton("Add Scanned Files...")
        self.btn_add_files.setStyleSheet(btn_style)
        self.btn_add_files.clicked.connect(self._add_files)

        self.btn_add_folder = QPushButton("Import Complete Folder...")
        self.btn_add_folder.setStyleSheet(btn_style)
        self.btn_add_folder.clicked.connect(self._add_folder)

        self.btn_start = QPushButton("Start Batch Processing")
        self.btn_start.setStyleSheet(btn_style.replace("#0E639C", "#107C41").replace("#1177BB", "#159D52"))
        self.btn_start.clicked.connect(self._start_batch)

        self.btn_cancel = QPushButton("Cancel Processing")
        self.btn_cancel.setStyleSheet(btn_style.replace("#0E639C", "#E81123").replace("#1177BB", "#F14C4C"))
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_batch)

        self.btn_clear = QPushButton("Clear Queue")
        self.btn_clear.setStyleSheet("background-color: #3E3E42; color: white; padding: 8px 14px; border-radius: 5px;")
        self.btn_clear.clicked.connect(self._clear_queue)

        btn_row.addWidget(self.btn_add_files)
        btn_row.addWidget(self.btn_add_folder)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch()

        layout.addLayout(btn_row)

        # Progress Section
        prog_frame = QFrame()
        prog_frame.setStyleSheet("background-color: #252526; border-radius: 6px; padding: 12px;")
        prog_layout = QVBoxLayout(prog_frame)

        self.lbl_progress = QLabel("Ready. Queue empty.")
        self.lbl_progress.setStyleSheet("color: #CCCCCC; font-size: 13px;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #0E639C;
                border-radius: 3px;
            }
        """)

        prog_layout.addWidget(self.lbl_progress)
        prog_layout.addWidget(self.progress_bar)
        layout.addWidget(prog_frame)

        # Batch Queue Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "File Name", "Size (KB)", "Processing Status"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #FFFFFF;
                gridline-color: #3E3E42;
                border: 1px solid #3E3E42;
            }
            QHeaderView::section {
                background-color: #2D2D30;
                color: #FFFFFF;
                font-weight: bold;
                padding: 6px;
            }
        """)
        layout.addWidget(self.table)

    def set_context(self, exam_id: int) -> None:
        """Sets active examination and loads key."""
        self.current_exam = self.repo.get_examination(exam_id)
        self.current_key = self.repo.get_latest_answer_key(exam_id)

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select OMR Images or PDFs", "",
            "Images and PDFs (*.jpg *.jpeg *.png *.tif *.tiff *.pdf)"
        )
        if files:
            for f in files:
                p = Path(f)
                if p not in self.queued_files:
                    self.queued_files.append(p)
            self._refresh_table()

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Folder of Scanned Sheets")
        if folder:
            p_folder = Path(folder)
            valid_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pdf"}
            for item in p_folder.iterdir():
                if item.is_file() and item.suffix.lower() in valid_exts:
                    if item not in self.queued_files:
                        self.queued_files.append(item)
            self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.queued_files))
        for row, path in enumerate(self.queued_files):
            size_kb = int(path.stat().st_size / 1024) if path.exists() else 0

            item_idx = QTableWidgetItem(str(row + 1))
            item_idx.setTextAlignment(Qt.AlignCenter)
            item_name = QTableWidgetItem(path.name)
            item_size = QTableWidgetItem(f"{size_kb:,} KB")
            item_size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item_status = QTableWidgetItem("QUEUED")
            item_status.setTextAlignment(Qt.AlignCenter)
            item_status.setForeground(QColor(180, 180, 180))

            self.table.setItem(row, 0, item_idx)
            self.table.setItem(row, 1, item_name)
            self.table.setItem(row, 2, item_size)
            self.table.setItem(row, 3, item_status)

        self.lbl_progress.setText(f"{len(self.queued_files)} sheets queued for processing.")

    def _clear_queue(self) -> None:
        self.queued_files.clear()
        self.table.setRowCount(0)
        self.progress_bar.setValue(0)
        self.lbl_progress.setText("Queue cleared.")

    def _start_batch(self) -> None:
        if not self.current_exam:
            QMessageBox.warning(self, "No Exam Active", "Please select or create an examination first in Setup.")
            return
        if not self.current_key:
            QMessageBox.warning(self, "No Answer Key", "Please import an answer key for this examination first.")
            return
        if not self.queued_files:
            QMessageBox.warning(self, "Empty Queue", "Please add at least one scanned sheet to process.")
            return

        self.btn_start.setEnabled(False)
        self.btn_add_files.setEnabled(False)
        self.btn_add_folder.setEnabled(False)
        self.btn_cancel.setEnabled(True)

        self.worker = BatchWorker(self.current_exam, self.current_key, self.queued_files)
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _cancel_batch(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.lbl_progress.setText("Cancelling batch processing...")
            self.btn_cancel.setEnabled(False)

    @Slot(int, int, str, str)
    def _on_worker_progress(self, current: int, total: int, filename: str, status: str) -> None:
        pct = int((current / total) * 100)
        self.progress_bar.setValue(pct)
        self.lbl_progress.setText(f"Processing {current}/{total}: {filename} — {status}")

        # Update row in table
        row = current - 1
        if 0 <= row < self.table.rowCount():
            item_status = self.table.item(row, 3)
            if item_status:
                item_status.setText(status)
                if status == "SUCCESS":
                    item_status.setForeground(QColor(16, 124, 65))
                elif status == "REVIEW_REQUIRED":
                    item_status.setForeground(QColor(216, 59, 1))
                else:
                    item_status.setForeground(QColor(232, 17, 35))

    @Slot(dict)
    def _on_worker_finished(self, summary: dict) -> None:
        self.btn_start.setEnabled(True)
        self.btn_add_files.setEnabled(True)
        self.btn_add_folder.setEnabled(True)
        self.btn_cancel.setEnabled(False)

        msg = (
            f"Batch completed.\n"
            f"Total: {summary['total']}\n"
            f"Successful: {summary['successful']}\n"
            f"Review Required: {summary['review_required']}\n"
            f"Failed: {summary['failed']}"
        )
        self.lbl_progress.setText(f"Batch completed. {summary['successful']} successful, {summary['review_required']} review required.")
        self.batchCompleted.emit()
        QMessageBox.information(self, "Batch Complete", msg)

