"""Answer-Key inspection, verification grid, manual adjustments, and approval locking."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QPushButton, QComboBox, QMessageBox, QFrame, QHeaderView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from app.models.entities import AnswerKey
from app.database.repository import Repository, repository


class AnswerKeyView(QWidget):
    """View to review extracted answers, make manual corrections, and approve/lock the key."""

    keyLocked = Signal(int)  # key_id

    def __init__(self, repo: Repository = repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.current_key: AnswerKey = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header Banner
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #252526; border-radius: 8px; padding: 14px;")
        h_layout = QHBoxLayout(header_frame)

        v_info = QVBoxLayout()
        self.lbl_title = QLabel("Answer-Key Verification & Audit Screen")
        self.lbl_title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self.lbl_title.setStyleSheet("color: #FFFFFF;")

        self.lbl_meta = QLabel("No active examination or answer key loaded.")
        self.lbl_meta.setStyleSheet("color: #CCCCCC; font-size: 13px;")

        v_info.addWidget(self.lbl_title)
        v_info.addWidget(self.lbl_meta)
        h_layout.addLayout(v_info)

        h_layout.addStretch()

        self.btn_lock = QPushButton("Approve & Lock Key")
        self.btn_lock.setStyleSheet("""
            QPushButton {
                background-color: #107C41;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #159D52; }
            QPushButton:disabled { background-color: #3E3E42; color: #888888; }
        """)
        self.btn_lock.clicked.connect(self._lock_key)
        h_layout.addWidget(self.btn_lock)

        layout.addWidget(header_frame)

        # Distribution Summary Bar
        self.lbl_dist = QLabel("Distribution: A: 0 | B: 0 | C: 0 | D: 0 | Missing: 0")
        self.lbl_dist.setStyleSheet("color: #00B294; font-weight: bold; font-size: 13px;")
        layout.addWidget(self.lbl_dist)

        # 160 Questions Table Grid (4 sets of columns side-by-side or tall table)
        # Using 8 columns: Q# | Option | Q# | Option | Q# | Option | Q# | Option (40 rows)
        self.table = QTableWidget(40, 8)
        self.table.setHorizontalHeaderLabels([
            "Q (1-40)", "Ans", "Q (41-80)", "Ans", "Q (81-120)", "Ans", "Q (121-160)", "Ans"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
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
                border: 1px solid #3E3E42;
            }
        """)
        layout.addWidget(self.table)

    def load_answer_key(self, exam_id: int) -> None:
        """Loads and populates the answer key for the specified examination."""
        key = self.repo.get_latest_answer_key(exam_id)
        if not key:
            self.current_key = None
            self.lbl_meta.setText(f"No answer key found for Examination ID #{exam_id}. Please import SA-08.pdf in Setup.")
            self.table.clearContents()
            self.btn_lock.setEnabled(False)
            return

        self.current_key = key
        lock_status = "LOCKED (Evaluation Certified)" if key.is_locked else "UNLOCKED (Review Mode)"
        self.lbl_meta.setText(f"Exam #{exam_id} | Version {key.version_number} | Hash: {key.version_hash[:16]}... | Status: {lock_status}")
        self.btn_lock.setEnabled(not key.is_locked)

        # Populate table
        counts = {"A": 0, "B": 0, "C": 0, "D": 0, "?": 0}

        for row in range(40):
            # Column set 1: Q 1..40
            q1 = row + 1
            opt1 = key.items.get(q1, "?")
            counts[opt1] = counts.get(opt1, 0) + 1
            self._set_cell(row, 0, str(q1), is_number=True)
            self._set_cell(row, 1, opt1, is_number=False, q_num=q1)

            # Column set 2: Q 41..80
            q2 = row + 41
            opt2 = key.items.get(q2, "?")
            counts[opt2] = counts.get(opt2, 0) + 1
            self._set_cell(row, 2, str(q2), is_number=True)
            self._set_cell(row, 3, opt2, is_number=False, q_num=q2)

            # Column set 3: Q 81..120
            q3 = row + 81
            opt3 = key.items.get(q3, "?")
            counts[opt3] = counts.get(opt3, 0) + 1
            self._set_cell(row, 4, str(q3), is_number=True)
            self._set_cell(row, 5, opt3, is_number=False, q_num=q3)

            # Column set 4: Q 121..160
            q4 = row + 121
            opt4 = key.items.get(q4, "?")
            counts[opt4] = counts.get(opt4, 0) + 1
            self._set_cell(row, 6, str(q4), is_number=True)
            self._set_cell(row, 7, opt4, is_number=False, q_num=q4)

        self.lbl_dist.setText(
            f"Distribution: A: {counts.get('A', 0)} ({counts.get('A',0)/1.6:.1f}%) | "
            f"B: {counts.get('B', 0)} ({counts.get('B',0)/1.6:.1f}%) | "
            f"C: {counts.get('C', 0)} ({counts.get('C',0)/1.6:.1f}%) | "
            f"D: {counts.get('D', 0)} ({counts.get('D',0)/1.6:.1f}%) | "
            f"Missing: {counts.get('?', 0)}"
        )

    def _set_cell(self, row: int, col: int, text: str, is_number: bool, q_num: int = 0) -> None:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        if is_number:
            item.setFlags(Qt.ItemIsEnabled)
            item.setBackground(QColor(37, 37, 38))
            item.setForeground(QColor(180, 180, 180))
        else:
            if self.current_key and self.current_key.is_locked:
                item.setFlags(Qt.ItemIsEnabled)
            else:
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsSelectable)
            # Color code answers
            color_map = {
                "A": QColor(0, 120, 215, 60),
                "B": QColor(104, 33, 122, 60),
                "C": QColor(0, 178, 148, 60),
                "D": QColor(216, 59, 1, 60)
            }
            item.setBackground(color_map.get(text, QColor(60, 60, 60)))
        self.table.setItem(row, col, item)

    def _lock_key(self) -> None:
        if not self.current_key:
            return
        reply = QMessageBox.question(
            self,
            "Confirm Answer Key Approval",
            "Are you sure you want to approve and lock this answer key?\n"
            "Once locked, the key becomes immutable and certified for final evaluation scoring.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self.repo.lock_answer_key(self.current_key.id)
            self.load_answer_key(self.current_key.exam_id)
            self.keyLocked.emit(self.current_key.id)
            QMessageBox.information(self, "Key Approved", "Answer key has been locked and certified for evaluation.")

