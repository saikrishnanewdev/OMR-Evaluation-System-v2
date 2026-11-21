"""Results and Ranking Table view with filtering, search, and audit inspector."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QLineEdit, QComboBox, QPushButton, QHeaderView, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from app.database.repository import Repository, repository
from app.models.entities import Examination, ProcessedSheet


class ResultsView(QWidget):
    """Sortable, searchable results table with certified examination ranks."""

    openReviewForSheet = Signal(int)

    def __init__(self, repo: Repository = repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.current_exam: Examination = None
        self.all_sheets: list[ProcessedSheet] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header Title
        title_label = QLabel("Student Examination Results & Certified Rankings")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title_label.setStyleSheet("color: #FFFFFF;")
        layout.addWidget(title_label)

        # Filter and Search Bar
        filter_bar = QFrame()
        filter_bar.setStyleSheet("background-color: #252526; border-radius: 6px; padding: 10px;")
        f_layout = QHBoxLayout(filter_bar)
        f_layout.setSpacing(12)

        lbl_search = QLabel("Search:")
        lbl_search.setStyleSheet("color: #CCCCCC; font-weight: 500;")
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter by Hall Ticket, Name, or File...")
        self.txt_search.setStyleSheet("background-color: #1E1E1E; color: white; border: 1px solid #3E3E42; padding: 6px; border-radius: 4px;")
        self.txt_search.textChanged.connect(self._apply_filter)

        lbl_status = QLabel("Status:")
        lbl_status.setStyleSheet("color: #CCCCCC; font-weight: 500;")
        self.combo_status = QComboBox()
        self.combo_status.addItems(["ALL", "SUCCESS / VERIFIED", "REVIEW_REQUIRED", "REJECTED"])
        self.combo_status.setStyleSheet("background-color: #1E1E1E; color: white; border: 1px solid #3E3E42; padding: 6px;")
        self.combo_status.currentTextChanged.connect(self._apply_filter)

        self.btn_refresh = QPushButton("Refresh Results")
        self.btn_refresh.setStyleSheet("background-color: #0E639C; color: white; padding: 6px 14px; border-radius: 4px;")
        self.btn_refresh.clicked.connect(self.reload_results)

        f_layout.addWidget(lbl_search)
        f_layout.addWidget(self.txt_search, 1)
        f_layout.addWidget(lbl_status)
        f_layout.addWidget(self.combo_status)
        f_layout.addWidget(self.btn_refresh)

        layout.addWidget(filter_bar)

        # Main Results Table (Columns strictly conforming to reference format)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "File",
            "Hall Ticket Number/Name",
            "Correct",
            "Correct Marks",
            "Wrong",
            "Unattempted",
            "Student Rank"
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
                padding: 8px;
            }
            QTableWidget::item:selected {
                background-color: #094771;
            }
        """)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self.table)

        self.lbl_summary = QLabel("Showing 0 students.")
        self.lbl_summary.setStyleSheet("color: #A0A0A0; font-size: 12px;")
        layout.addWidget(self.lbl_summary)

    def set_context(self, exam_id: int) -> None:
        self.current_exam = self.repo.get_examination(exam_id)
        self.reload_results()

    def reload_results(self) -> None:
        if not self.current_exam:
            return
        self.all_sheets = self.repo.list_sheets(self.current_exam.id)
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.txt_search.text().strip().lower()
        status_filter = self.combo_status.currentText()

        filtered = []
        for s in self.all_sheets:
            # Status filter
            if status_filter == "SUCCESS / VERIFIED" and s.status not in ("SUCCESS", "VERIFIED"):
                continue
            if status_filter == "REVIEW_REQUIRED" and s.status != "REVIEW_REQUIRED":
                continue
            if status_filter == "REJECTED" and s.status != "REJECTED":
                continue

            # Text search filter
            if query:
                match = (
                    query in s.file_name.lower() or
                    query in s.hall_ticket_final.lower() or
                    query in s.candidate_name_final.lower()
                )
                if not match:
                    continue

            filtered.append(s)

        self.table.setRowCount(len(filtered))
        for row_idx, s in enumerate(filtered):
            c_file = QTableWidgetItem(s.file_name)
            c_id = QTableWidgetItem(s.display_identifier)
            c_id.setData(Qt.UserRole, s.id)

            c_corr = QTableWidgetItem(str(s.correct_count))
            c_corr.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            c_marks = QTableWidgetItem(f"{s.total_marks:.2f}")
            c_marks.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            c_wrong = QTableWidgetItem(str(s.wrong_count))
            c_wrong.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            c_unatt = QTableWidgetItem(str(s.unattempted_count))
            c_unatt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            c_rank = QTableWidgetItem(str(s.student_rank) if s.student_rank > 0 else "-")
            c_rank.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            c_rank.setFont(QFont("Segoe UI", 10, QFont.Bold))

            self.table.setItem(row_idx, 0, c_file)
            self.table.setItem(row_idx, 1, c_id)
            self.table.setItem(row_idx, 2, c_corr)
            self.table.setItem(row_idx, 3, c_marks)
            self.table.setItem(row_idx, 4, c_wrong)
            self.table.setItem(row_idx, 5, c_unatt)
            self.table.setItem(row_idx, 6, c_rank)

        self.lbl_summary.setText(f"Showing {len(filtered)} evaluated students. Double-click row to open in Review Workspace.")

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        row = item.row()
        id_item = self.table.item(row, 1)
        if id_item:
            sheet_id = id_item.data(Qt.UserRole)
            if sheet_id:
                self.openReviewForSheet.emit(sheet_id)

