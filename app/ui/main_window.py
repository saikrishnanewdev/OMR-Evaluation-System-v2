"""Main application window with sidebar navigation, tab coordination, and system status bar."""
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QPushButton, QLabel, QFrame, QStatusBar, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QColor
from app.database.connection import db_manager
from app.database.repository import Repository, repository
from app.ui.views.dashboard_view import DashboardView
from app.ui.views.exam_setup_view import ExamSetupView
from app.ui.views.answer_key_view import AnswerKeyView
from app.ui.views.batch_import_view import BatchImportView
from app.ui.views.manual_review_view import ManualReviewView
from app.ui.views.results_view import ResultsView
from app.ui.views.export_view import ExportView


class MainWindow(QMainWindow):
    """Main desktop application window managing tabs and global examination state."""

    def __init__(self, repo: Repository = repository):
        super().__init__()
        self.repo = repo
        self.active_exam_id: int = 1
        self.setWindowTitle("Offline OMR Evaluation System for Windows — v1.0")
        self.resize(1366, 820)
        self.setMinimumSize(1100, 700)
        self._setup_ui()
        self._load_initial_state()

    def _setup_ui(self) -> None:
        # Central widget with horizontal sidebar layout
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Sidebar Navigation
        sidebar = QFrame()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border-right: 1px solid #3E3E42;
            }
        """)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 16, 12, 16)
        sb_layout.setSpacing(6)

        # App Brand Header
        app_title = QLabel("OMR EVALUATOR")
        app_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        app_title.setStyleSheet("color: #0078D4; padding: 6px 10px;")
        sb_layout.addWidget(app_title)

        app_sub = QLabel("Windows Offline Engine")
        app_sub.setStyleSheet("color: #888888; font-size: 11px; padding-left: 10px; margin-bottom: 12px;")
        sb_layout.addWidget(app_sub)

        # Nav Buttons
        self.nav_buttons: list[QPushButton] = []
        nav_items = [
            ("Dashboard", "dashboard"),
            ("Examination Setup", "setup"),
            ("Answer Key", "key"),
            ("Batch Processing", "batch"),
            ("Manual Review", "review"),
            ("Results & Ranking", "results"),
            ("Export to Excel", "export"),
        ]

        for label, tag in nav_items:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #CCCCCC;
                    border: none;
                    border-radius: 5px;
                    padding: 10px 14px;
                    text-align: left;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #2D2D30;
                    color: #FFFFFF;
                }
                QPushButton:checked {
                    background-color: #094771;
                    color: #FFFFFF;
                    font-weight: bold;
                }
            """)
            btn.clicked.connect(lambda checked, t=tag: self._on_nav_clicked(t))
            sb_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sb_layout.addStretch()

        # Database Backup & Restore buttons at bottom of sidebar
        btn_backup = QPushButton("Backup Database...")
        btn_backup.setStyleSheet("background-color: #2D2D30; color: #CCCCCC; border: 1px solid #3E3E42; border-radius: 4px; padding: 6px;")
        btn_backup.clicked.connect(self._backup_db)
        sb_layout.addWidget(btn_backup)

        btn_restore = QPushButton("Restore Database...")
        btn_restore.setStyleSheet("background-color: #2D2D30; color: #CCCCCC; border: 1px solid #3E3E42; border-radius: 4px; padding: 6px;")
        btn_restore.clicked.connect(self._restore_db)
        sb_layout.addWidget(btn_restore)

        main_layout.addWidget(sidebar)

        # 2. Main Stacked Content Views
        self.stacked = QStackedWidget()
        self.stacked.setStyleSheet("background-color: #181818;")

        self.view_dashboard = DashboardView(self.repo)
        self.view_dashboard.navigateTo.connect(self._navigate_to_tag)

        self.view_setup = ExamSetupView(self.repo)
        self.view_setup.examSelected.connect(self._on_exam_selected)

        self.view_key = AnswerKeyView(self.repo)
        self.view_batch = BatchImportView(self.repo)
        self.view_batch.batchCompleted.connect(self._on_batch_completed)

        self.view_review = ManualReviewView(self.repo)
        self.view_review.sheetVerified.connect(self._on_sheet_verified)

        self.view_results = ResultsView(self.repo)
        self.view_results.openReviewForSheet.connect(self._open_sheet_in_review)

        self.view_export = ExportView(self.repo)

        self.stacked.addWidget(self.view_dashboard)  # 0
        self.stacked.addWidget(self.view_setup)      # 1
        self.stacked.addWidget(self.view_key)        # 2
        self.stacked.addWidget(self.view_batch)      # 3
        self.stacked.addWidget(self.view_review)     # 4
        self.stacked.addWidget(self.view_results)    # 5
        self.stacked.addWidget(self.view_export)     # 6

        main_layout.addWidget(self.stacked)

        # 3. Status Bar
        status = QStatusBar()
        status.setStyleSheet("background-color: #0078D4; color: #FFFFFF; font-weight: 500;")
        self.setStatusBar(status)
        self.lbl_status_exam = QLabel("Active Exam: None")
        self.lbl_status_exam.setStyleSheet("color: #FFFFFF; font-weight: bold; margin-left: 10px;")
        self.lbl_status_mode = QLabel("Mode: 100% Offline (No Cloud APIs)")
        self.lbl_status_mode.setStyleSheet("color: #DDF0FF; margin-right: 20px;")
        status.addWidget(self.lbl_status_exam, 1)
        status.addPermanentWidget(self.lbl_status_mode)

    def _load_initial_state(self) -> None:
        """Loads default examination or creates initial reference exam."""
        exams = self.repo.list_examinations()
        if exams:
            self.active_exam_id = exams[0].id
            self._propagate_active_exam(self.active_exam_id)
        else:
            # Auto-create the reference AP DSC exam if DB is fresh
            from app.models.entities import Examination
            ex_id = self.repo.create_examination(Examination(
                code="AP_DSC_SA08",
                name="AP DSC 2026 SA(Social) 3.0 Divisional Test-08",
                total_questions=160,
                correct_mark=0.50,
                wrong_mark=0.00,
                unattempted_mark=0.00,
                template_name="OMR_AP_DSC_160_V1",
                status="ACTIVE"
            ))
            self.active_exam_id = ex_id
            self._propagate_active_exam(ex_id)

        self._on_nav_clicked("dashboard")

    def _propagate_active_exam(self, exam_id: int) -> None:
        self.active_exam_id = exam_id
        exam = self.repo.get_examination(exam_id)
        if exam:
            self.lbl_status_exam.setText(f"Active Exam: {exam.name} ({exam.code})")
        self.view_key.load_answer_key(exam_id)
        self.view_batch.set_context(exam_id)
        self.view_review.set_context(exam_id)
        self.view_results.set_context(exam_id)
        self.view_export.set_context(exam_id)
        self.view_dashboard.refresh_metrics()

    def _on_exam_selected(self, exam_id: int) -> None:
        self._propagate_active_exam(exam_id)

    def _on_batch_completed(self) -> None:
        self.view_dashboard.refresh_metrics()
        self.view_results.reload_results()
        self.view_review.reload_sheets()

    def _on_sheet_verified(self, sheet_id: int) -> None:
        self.view_dashboard.refresh_metrics()
        self.view_results.reload_results()

    def _open_sheet_in_review(self, sheet_id: int) -> None:
        self._navigate_to_tag("review")
        idx = self.view_review.combo_sheets.findData(sheet_id)
        if idx >= 0:
            self.view_review.combo_sheets.setCurrentIndex(idx)

    def _on_nav_clicked(self, tag: str) -> None:
        mapping = {
            "dashboard": (0, 0),
            "setup": (1, 1),
            "key": (2, 2),
            "batch": (3, 3),
            "review": (4, 4),
            "results": (5, 5),
            "export": (6, 6)
        }
        page_idx, btn_idx = mapping.get(tag, (0, 0))
        self.stacked.setCurrentIndex(page_idx)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == btn_idx)

        # Refresh metrics when returning to dashboard
        if tag == "dashboard":
            self.view_dashboard.refresh_metrics()
        elif tag == "results":
            self.view_results.reload_results()

    def _navigate_to_tag(self, tag: str) -> None:
        self._on_nav_clicked(tag)

    def _backup_db(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Backup Database to File", "omr_evaluation_backup.db", "SQLite Database (*.db)"
        )
        if file_path:
            try:
                db_manager.backup_database(Path(file_path))
                QMessageBox.information(self, "Backup Successful", f"Database backed up successfully to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Backup Failed", f"Failed to backup database: {e}")

    def _restore_db(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Restore Database from File", "", "SQLite Database (*.db)"
        )
        if file_path:
            reply = QMessageBox.warning(
                self, "Confirm Database Restore",
                "Restoring the database will replace all current examinations and results.\nAre you sure you want to proceed?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                try:
                    db_manager.restore_database(Path(file_path))
                    self._load_initial_state()
                    QMessageBox.information(self, "Restore Complete", "Database restored successfully.")
                except Exception as e:
                    QMessageBox.critical(self, "Restore Failed", f"Failed to restore database: {e}")

