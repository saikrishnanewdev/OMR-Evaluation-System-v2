"""Dashboard view displaying live KPIs, database summary metrics, and quick actions."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QSpacerItem
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from app.database.repository import Repository, repository


class MetricCard(QFrame):
    """Modern flat KPI display card."""

    def __init__(self, title: str, initial_value: str = "0", accent_color: str = "#0078D4", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            MetricCard {{
                background-color: #252526;
                border: 1px solid #3E3E42;
                border-radius: 8px;
                padding: 16px;
            }}
            QLabel#Title {{
                color: #A0A0A0;
                font-size: 13px;
                font-weight: 500;
            }}
            QLabel#Value {{
                color: {accent_color};
                font-size: 32px;
                font-weight: bold;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 12, 12, 12)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("Title")

        self.value_label = QLabel(initial_value)
        self.value_label.setObjectName("Value")

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, val: str) -> None:
        self.value_label.setText(str(val))


class DashboardView(QWidget):
    """Main dashboard displaying database statistics and workflow navigation buttons."""

    navigateTo = Signal(str)  # 'setup', 'batch', 'review', 'results', 'export'

    def __init__(self, repo: Repository = repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self._setup_ui()
        self.refresh_metrics()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        # Header Title
        title_label = QLabel("Examination Evaluation Dashboard")
        title_font = QFont("Segoe UI", 20, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #FFFFFF;")
        layout.addWidget(title_label)

        sub_label = QLabel("System Status: 100% Offline | Windows Production OMR Engine")
        sub_label.setStyleSheet("color: #00B294; font-size: 13px; font-weight: 500;")
        layout.addWidget(sub_label)

        # KPI Cards Grid
        grid_layout = QGridLayout()
        grid_layout.setSpacing(16)

        self.card_exams = MetricCard("Total Examinations", "0", "#0078D4")
        self.card_sheets = MetricCard("Total Sheets Imported", "0", "#68217A")
        self.card_success = MetricCard("Successfully Processed", "0", "#107C41")
        self.card_review = MetricCard("Manual Review Required", "0", "#D83B01")
        self.card_rejected = MetricCard("Rejected Sheets", "0", "#E81123")
        self.card_evaluated = MetricCard("Evaluated & Ranked", "0", "#008272")

        grid_layout.addWidget(self.card_exams, 0, 0)
        grid_layout.addWidget(self.card_sheets, 0, 1)
        grid_layout.addWidget(self.card_success, 0, 2)
        grid_layout.addWidget(self.card_review, 1, 0)
        grid_layout.addWidget(self.card_rejected, 1, 1)
        grid_layout.addWidget(self.card_evaluated, 1, 2)

        layout.addLayout(grid_layout)

        # Quick Actions Frame
        actions_frame = QFrame()
        actions_frame.setStyleSheet("""
            QFrame {
                background-color: #2D2D30;
                border: 1px solid #3E3E42;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        actions_layout = QVBoxLayout(actions_frame)
        actions_title = QLabel("Quick Actions")
        actions_title.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: bold; margin-bottom: 10px;")
        actions_layout.addWidget(actions_title)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        btn_style = """
            QPushButton {
                background-color: #0E639C;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 10px 18px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1177BB;
            }
            QPushButton:pressed {
                background-color: #094771;
            }
        """

        self.btn_new_exam = QPushButton("Create / Configure Exam")
        self.btn_new_exam.setStyleSheet(btn_style)
        self.btn_new_exam.clicked.connect(lambda: self.navigateTo.emit("setup"))

        self.btn_import_batch = QPushButton("Import & Process Batch")
        self.btn_import_batch.setStyleSheet(btn_style)
        self.btn_import_batch.clicked.connect(lambda: self.navigateTo.emit("batch"))

        self.btn_manual_review = QPushButton("Open Review Queue")
        self.btn_manual_review.setStyleSheet(btn_style.replace("#0E639C", "#D83B01").replace("#1177BB", "#EA4A1F"))
        self.btn_manual_review.clicked.connect(lambda: self.navigateTo.emit("review"))

        self.btn_export = QPushButton("Export Results to Excel")
        self.btn_export.setStyleSheet(btn_style.replace("#0E639C", "#107C41").replace("#1177BB", "#159D52"))
        self.btn_export.clicked.connect(lambda: self.navigateTo.emit("export"))

        btn_row.addWidget(self.btn_new_exam)
        btn_row.addWidget(self.btn_import_batch)
        btn_row.addWidget(self.btn_manual_review)
        btn_row.addWidget(self.btn_export)
        btn_row.addStretch()

        actions_layout.addLayout(btn_row)
        layout.addWidget(actions_frame)

        layout.addStretch()

    def refresh_metrics(self) -> None:
        """Queries the SQLite database and updates all card values."""
        stats = self.repo.get_dashboard_stats()
        self.card_exams.set_value(str(stats.get("total_examinations", 0)))
        self.card_sheets.set_value(str(stats.get("total_sheets", 0)))
        self.card_success.set_value(str(stats.get("success_count", 0)))
        self.card_review.set_value(str(stats.get("review_count", 0)))
        self.card_rejected.set_value(str(stats.get("rejected_count", 0)))
        self.card_evaluated.set_value(str(stats.get("evaluated_count", 0)))

