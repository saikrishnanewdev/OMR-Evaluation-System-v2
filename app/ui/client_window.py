"""
Simple, modern client UI for offline OMR Evaluation and Student Identity Extraction.
Designed for ease of use by non-technical operators with high visual clarity.

Features:
  1. Input Selection: Batch folder, Answer Key PDF, Student Roster Excel.
     - Auto-detects key PDF and roster Excel in the selected folder.
     - Prompts for missing files on-screen with one-click browse buttons.
  2. Output Selection: Configurable Excel path for results.
  3. Real-Time Execution: Progress bar, live status, instant statistics.
  4. Competition Results Table: Sortable, color-coded, with one-click Excel open.
  5. Interactive Review Pallet: Side-by-side processed crops (HT + Name),
     editable correction fields, and one-click Excel sync.
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QProgressBar, QTableWidget,
    QTableWidgetItem, QFileDialog, QTabWidget, QSplitter, QListWidget,
    QListWidgetItem, QFrame, QScrollArea, QHeaderView, QMessageBox,
    QDoubleSpinBox, QSpinBox, QComboBox
)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QSize, QTimer, QPoint
from PySide6.QtGui import QFont, QPixmap, QColor, QIcon, QPainter, QPolygon

import pandas as pd
import openpyxl
from openpyxl.styles import Font as XlFont, PatternFill, Alignment, Border, Side

from extract_identities_to_excel import (
    process_folder, detect_and_flag_duplicate_hall_tickets,
    rank_results, export_results_to_excel
)
from app.security.license_manager import license_manager
from app.ui.license_dialog import LicenseDialog


def get_or_create_spin_arrow_icons():
    """Returns (up_path, down_path) for spinbox arrow icons, creating them if needed."""
    from app.config.constants import BUNDLE_DIR, APP_ROOT
    candidates = [
        BUNDLE_DIR / "resources",
        APP_ROOT / "resources",
        Path(__file__).resolve().parent.parent / "resources",
        Path(__file__).resolve().parent.parent.parent / "resources",
    ]
    target_dir = None
    for c in candidates:
        if c.exists():
            target_dir = c
            break
    if target_dir is None:
        target_dir = APP_ROOT / "resources"
        target_dir.mkdir(parents=True, exist_ok=True)

    up_file = target_dir / "spin_up.png"
    down_file = target_dir / "spin_down.png"

    if not up_file.exists() or not down_file.exists() or up_file.stat().st_size == 0:
        # Crisp white up-arrow triangle
        pm_up = QPixmap(16, 16)
        pm_up.fill(Qt.transparent)
        p = QPainter(pm_up)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#E6EDF3"))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygon([QPoint(4, 10), QPoint(12, 10), QPoint(8, 5)]))
        p.end()
        pm_up.save(str(up_file))

        # Crisp white down-arrow triangle
        pm_down = QPixmap(16, 16)
        pm_down.fill(Qt.transparent)
        p = QPainter(pm_down)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#E6EDF3"))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygon([QPoint(4, 6), QPoint(12, 6), QPoint(8, 11)]))
        p.end()
        pm_down.save(str(down_file))

    return up_file.as_posix(), down_file.as_posix()


class BatchWorkerThread(QThread):
    """Executes batch OMR evaluation and OCR in a background thread."""
    progress = Signal(int, int, str, str)  # (current, total, file_name, status_msg)
    finished = Signal(bool, list, str, str)  # (success, results, excel_path, error_msg)

    def __init__(
        self,
        target_folder: Path,
        output_excel: Optional[Path],
        key_file: Optional[str],
        roster_file: Optional[str],
        correct_mark: Optional[float] = None,
        wrong_mark: float = 0.00,
        unattempted_mark: float = 0.00,
        from_question: int = 1,
        to_question: Optional[int] = None,
        reading_mode: str = "auto"
    ):
        super().__init__()
        self.target_folder = target_folder
        self.output_excel = output_excel
        self.key_file = key_file
        self.roster_file = roster_file
        self.correct_mark = correct_mark
        self.wrong_mark = wrong_mark
        self.unattempted_mark = unattempted_mark
        self.from_question = from_question
        self.to_question = to_question
        self.reading_mode = reading_mode

    def run(self):
        try:
            def on_progress(cur, tot, fn, msg):
                self.progress.emit(cur, tot, fn, msg)

            res = process_folder(
                target_folder=self.target_folder,
                output_excel=self.output_excel,
                key_file=self.key_file,
                roster_file=self.roster_file,
                progress_callback=on_progress,
                correct_mark=self.correct_mark,
                wrong_mark=self.wrong_mark,
                unattempted_mark=self.unattempted_mark,
                from_question=self.from_question,
                to_question=self.to_question,
                reading_mode=self.reading_mode
            )

            if isinstance(res, tuple) and len(res) == 3:
                success, results, save_path = res
                if success:
                    self.finished.emit(True, results, str(save_path), "")
                else:
                    self.finished.emit(False, [], "", str(save_path))
            elif isinstance(res, tuple) and len(res) == 2:
                success, results = res
                self.finished.emit(success, results, "", "")
            elif res is False:
                self.finished.emit(False, [], "", "No scanned OMR sheet images found in the selected folder.")
            elif res is True:
                self.finished.emit(True, [], "", "")
            else:
                self.finished.emit(False, [], "", "Batch evaluation failed or returned an unexpected result.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, [], "", str(e))


class ClientWindow(QMainWindow):
    """Main client evaluation interface."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Offline OMR Evaluation & Identity System - Client Edition")
        self.resize(1280, 840)
        self.setMinimumSize(1050, 700)

        # Set professional window icon
        from app.config.constants import BUNDLE_DIR, APP_ROOT
        candidates = [
            BUNDLE_DIR / "resources" / "app_icon.png",
            BUNDLE_DIR / "resources" / "app_icon.ico",
            APP_ROOT / "resources" / "app_icon.png",
            Path(__file__).resolve().parent.parent / "resources" / "app_icon.png",
            Path(__file__).resolve().parent.parent.parent / "resources" / "app_icon.png",
        ]
        for c in candidates:
            if c.exists():
                self.setWindowIcon(QIcon(str(c)))
                break

        self.batch_folder: Optional[Path] = None
        self.results: List[Dict[str, Any]] = []
        self.excel_path: Optional[Path] = None
        self.worker: Optional[BatchWorkerThread] = None
        self.current_review_index: int = -1
        self.review_records: List[Dict[str, Any]] = []

        self._setup_ui()

        # Check if license is expired on launch
        if license_manager.get_status()["status"] == "EXPIRED":
            QTimer.singleShot(150, lambda: self._open_license_dialog(force_lock=True))

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        # Header Title Banner
        header = QFrame()
        header.setStyleSheet("background-color: #1F242B; border-radius: 8px; padding: 6px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 6, 12, 6)

        title_lbl = QLabel("🎯 OMR EVALUATION & STUDENT IDENTITY SYSTEM")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title_lbl.setStyleSheet("color: #00A6FB;")
        h_layout.addWidget(title_lbl)

        h_layout.addStretch()

        badge = QLabel("100% Offline • High Accuracy Engine")
        badge.setStyleSheet("color: #A0AAB5; font-size: 11px; margin-right: 8px;")
        h_layout.addWidget(badge)

        self.btn_license = QPushButton("🔑 License Status")
        self.btn_license.setStyleSheet("padding: 4px 12px; border-radius: 4px; font-size: 11px; font-weight: bold;")
        self.btn_license.clicked.connect(self._open_license_dialog)
        h_layout.addWidget(self.btn_license)
        self._update_license_ui()

        main_layout.addWidget(header)

        # Tabs: 1) Batch Evaluation & Results, 2) Review Pallet
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #333940;
                background-color: #16191D;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #21262D;
                color: #C9D1D9;
                padding: 10px 22px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
                font-size: 12px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #0078D4;
                color: #FFFFFF;
            }
            QTabBar::tab:hover:!selected {
                background: #30363D;
            }
        """)

        self.tab_eval = QWidget()
        self.tab_review = QWidget()

        self._build_eval_tab()
        self._build_review_pallet_tab()

        self.tabs.addTab(self.tab_eval, "📋 Batch Evaluation")
        self.tabs.addTab(self.tab_review, "🔍 Review Pallet (0 Pending)")

        main_layout.addWidget(self.tabs, stretch=1)

    def _build_eval_tab(self):
        layout = QVBoxLayout(self.tab_eval)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # 1. Inputs Card
        inputs_box = QFrame()
        inputs_box.setStyleSheet("background-color: #21262D; border: 1px solid #30363D; border-radius: 8px;")
        grid = QGridLayout(inputs_box)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        # Batch Folder Row
        grid.addWidget(QLabel("1. Batch OMR Scans Folder:"), 0, 0)
        self.txt_batch = QLineEdit()
        self.txt_batch.setPlaceholderText("Select folder containing scanned OMR sheet images (e.g., C:\\Scans\\KNL_SGT)...")
        self.txt_batch.setStyleSheet("background-color: #0D1117; color: #FFFFFF; border: 1px solid #30363D; padding: 6px; border-radius: 4px;")
        grid.addWidget(self.txt_batch, 0, 1)

        btn_browse_batch = QPushButton("Browse Folder...")
        btn_browse_batch.setStyleSheet("background-color: #0969DA; color: white; padding: 6px 14px; font-weight: bold; border-radius: 4px;")
        btn_browse_batch.clicked.connect(self._browse_batch_folder)
        grid.addWidget(btn_browse_batch, 0, 2)

        # Answer Key Row
        grid.addWidget(QLabel("2. Answer Key PDF (Optional):"), 1, 0)
        self.txt_key = QLineEdit()
        self.txt_key.setPlaceholderText("Master Answer Key PDF (Auto-detected from batch folder, or browse manually)...")
        self.txt_key.setStyleSheet("background-color: #0D1117; color: #FFFFFF; border: 1px solid #30363D; padding: 6px; border-radius: 4px;")
        grid.addWidget(self.txt_key, 1, 1)

        btn_browse_key = QPushButton("Browse PDF...")
        btn_browse_key.setStyleSheet("background-color: #21262D; color: #E6EDF3; border: 1px solid #30363D; padding: 6px 14px; border-radius: 4px;")
        btn_browse_key.clicked.connect(self._browse_key_file)
        grid.addWidget(btn_browse_key, 1, 2)

        # Student Roster Row
        grid.addWidget(QLabel("3. Student Roster Excel (Optional):"), 2, 0)
        self.txt_roster = QLineEdit()
        self.txt_roster.setPlaceholderText("Student Roster with Roll No & Name (Auto-detected from folder, or browse manually)...")
        self.txt_roster.setStyleSheet("background-color: #0D1117; color: #FFFFFF; border: 1px solid #30363D; padding: 6px; border-radius: 4px;")
        grid.addWidget(self.txt_roster, 2, 1)

        btn_browse_roster = QPushButton("Browse Excel...")
        btn_browse_roster.setStyleSheet("background-color: #21262D; color: #E6EDF3; border: 1px solid #30363D; padding: 6px 14px; border-radius: 4px;")
        btn_browse_roster.clicked.connect(self._browse_roster_file)
        grid.addWidget(btn_browse_roster, 2, 2)

        # Results Output Path Row
        grid.addWidget(QLabel("4. Save Results Excel To:"), 3, 0)
        self.txt_output = QLineEdit()
        self.txt_output.setPlaceholderText("Full destination path for generated OMR_Student_Identities.xlsx...")
        self.txt_output.setStyleSheet("background-color: #0D1117; color: #FFFFFF; border: 1px solid #30363D; padding: 6px; border-radius: 4px;")
        grid.addWidget(self.txt_output, 3, 1)

        btn_browse_out = QPushButton("Change Path...")
        btn_browse_out.setStyleSheet("background-color: #21262D; color: #E6EDF3; border: 1px solid #30363D; padding: 6px 14px; border-radius: 4px;")
        btn_browse_out.clicked.connect(self._browse_output_excel)
        grid.addWidget(btn_browse_out, 3, 2)

        # Reading Mode Row — lets the user compare Fixed vs Dynamic
        # reading on their own sheets before the app is finalised.
        # Auto = fixed unless the warped top is cut off (old behaviour).
        grid.addWidget(QLabel("5. Reading Mode:"), 4, 0)
        self.cmb_reading_mode = QComboBox()
        self.cmb_reading_mode.addItem("Auto (recommended)", "auto")
        self.cmb_reading_mode.addItem("Dynamic (find positions from sheet)", "dynamic")
        self.cmb_reading_mode.addItem("Fixed (fixed template)", "fixed")
        self.cmb_reading_mode.setToolTip(
            "Auto: fixed template, dynamic only when the top of the sheet is cut off.\n"
            "Dynamic: always find the hall ticket, name and bubbles from the sheet itself.\n"
            "Fixed: always use the fixed template. The Excel output records the mode used per sheet.")
        self.cmb_reading_mode.setStyleSheet("background-color: #0D1117; color: #FFFFFF; border: 1px solid #30363D; padding: 6px; border-radius: 4px;")
        grid.addWidget(self.cmb_reading_mode, 4, 1, 1, 2)

        # Missing File Banner (shows only when key or roster missing from folder)
        self.banner_missing = QFrame()
        self.banner_missing.setStyleSheet("background-color: #2B1D0E; border: 1px solid #9E6A03; border-radius: 6px; padding: 4px;")
        self.banner_missing.setVisible(False)
        bm_layout = QHBoxLayout(self.banner_missing)
        bm_layout.setContentsMargins(10, 4, 10, 4)

        self.lbl_banner_msg = QLabel("ℹ️ File notification")
        self.lbl_banner_msg.setStyleSheet("color: #F0B72F; font-size: 11px;")
        bm_layout.addWidget(self.lbl_banner_msg, stretch=1)

        self.btn_banner_action1 = QPushButton("Select Key PDF")
        self.btn_banner_action1.setStyleSheet("background-color: #9E6A03; color: white; padding: 3px 10px; border-radius: 4px; font-size: 11px;")
        self.btn_banner_action1.clicked.connect(self._browse_key_file)
        bm_layout.addWidget(self.btn_banner_action1)

        self.btn_banner_action2 = QPushButton("Select Roster Excel")
        self.btn_banner_action2.setStyleSheet("background-color: #9E6A03; color: white; padding: 3px 10px; border-radius: 4px; font-size: 11px;")
        self.btn_banner_action2.clicked.connect(self._browse_roster_file)
        bm_layout.addWidget(self.btn_banner_action2)

        grid.addWidget(self.banner_missing, 5, 0, 1, 3)

        layout.addWidget(inputs_box)

        # 1b. Marking Scheme & Evaluation Scope Configuration
        marking_frame = QFrame()
        marking_frame.setStyleSheet("background-color: #21262D; border: 1px solid #30363D; border-radius: 8px;")
        m_grid = QGridLayout(marking_frame)
        m_grid.setContentsMargins(16, 10, 16, 10)
        m_grid.setHorizontalSpacing(16)
        m_grid.setVerticalSpacing(8)

        up_arrow_path, down_arrow_path = get_or_create_spin_arrow_icons()

        spin_style = f"""
            QDoubleSpinBox, QSpinBox {{
                background-color: #0D1117;
                color: #FFFFFF;
                border: 1px solid #30363D;
                padding: 4px 8px;
                border-radius: 4px;
                font-family: Consolas, monospace;
                font-size: 12px;
                font-weight: bold;
                min-width: 85px;
            }}
            QDoubleSpinBox:focus, QSpinBox:focus {{
                border: 1px solid #388BFD;
            }}
            QDoubleSpinBox::up-button, QSpinBox::up-button {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #30363D;
                border-bottom: 1px solid #30363D;
                background-color: #161B22;
            }}
            QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover {{
                background-color: #388BFD;
            }}
            QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {{
                image: url({up_arrow_path});
                width: 9px;
                height: 9px;
            }}
            QDoubleSpinBox::down-button, QSpinBox::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 20px;
                border-left: 1px solid #30363D;
                background-color: #161B22;
            }}
            QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover {{
                background-color: #388BFD;
            }}
            QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {{
                image: url({down_arrow_path});
                width: 9px;
                height: 9px;
            }}
        """

        # Row 0: Correct, Wrong, No Response
        lbl_c = QLabel("Correct Response:")
        lbl_c.setStyleSheet("color: #E6EDF3; font-weight: bold; font-size: 11px;")
        m_grid.addWidget(lbl_c, 0, 0, Qt.AlignRight | Qt.AlignVCenter)

        self.spn_correct = QDoubleSpinBox()
        self.spn_correct.setStyleSheet(spin_style)
        self.spn_correct.setRange(0.00, 10.00)
        self.spn_correct.setSingleStep(0.25)
        self.spn_correct.setDecimals(2)
        self.spn_correct.setValue(1.00)
        m_grid.addWidget(self.spn_correct, 0, 1)

        lbl_w = QLabel("Wrong Response:")
        lbl_w.setStyleSheet("color: #E6EDF3; font-weight: bold; font-size: 11px;")
        m_grid.addWidget(lbl_w, 0, 2, Qt.AlignRight | Qt.AlignVCenter)

        self.spn_wrong = QDoubleSpinBox()
        self.spn_wrong.setStyleSheet(spin_style)
        self.spn_wrong.setRange(-10.00, 0.00)
        self.spn_wrong.setSingleStep(0.01)
        self.spn_wrong.setDecimals(2)
        self.spn_wrong.setValue(0.00)
        m_grid.addWidget(self.spn_wrong, 0, 3)

        lbl_u = QLabel("No Response:")
        lbl_u.setStyleSheet("color: #E6EDF3; font-weight: bold; font-size: 11px;")
        m_grid.addWidget(lbl_u, 0, 4, Qt.AlignRight | Qt.AlignVCenter)

        self.spn_unattempted = QDoubleSpinBox()
        self.spn_unattempted.setStyleSheet(spin_style)
        self.spn_unattempted.setRange(-5.00, 5.00)
        self.spn_unattempted.setSingleStep(0.01)
        self.spn_unattempted.setDecimals(2)
        self.spn_unattempted.setValue(0.00)
        m_grid.addWidget(self.spn_unattempted, 0, 5)

        # Row 1: From Row No, To Row No, Update Marks
        lbl_from = QLabel("From Row No.:")
        lbl_from.setStyleSheet("color: #E6EDF3; font-weight: bold; font-size: 11px;")
        m_grid.addWidget(lbl_from, 1, 0, Qt.AlignRight | Qt.AlignVCenter)

        self.spn_from_q = QSpinBox()
        self.spn_from_q.setStyleSheet(spin_style)
        self.spn_from_q.setRange(1, 300)
        self.spn_from_q.setValue(1)
        m_grid.addWidget(self.spn_from_q, 1, 1)

        lbl_to = QLabel("To Row No.:")
        lbl_to.setStyleSheet("color: #E6EDF3; font-weight: bold; font-size: 11px;")
        m_grid.addWidget(lbl_to, 1, 2, Qt.AlignRight | Qt.AlignVCenter)

        self.spn_to_q = QSpinBox()
        self.spn_to_q.setStyleSheet(spin_style)
        self.spn_to_q.setRange(1, 300)
        self.spn_to_q.setValue(160)
        m_grid.addWidget(self.spn_to_q, 1, 3)

        self.btn_update_marks = QPushButton("Update Marks")
        self.btn_update_marks.setStyleSheet("""
            QPushButton {
                background-color: #0969DA;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1F6FEB; }
        """)
        self.btn_update_marks.clicked.connect(self._recalculate_marks)
        m_grid.addWidget(self.btn_update_marks, 1, 5)

        layout.addWidget(marking_frame)

        # 2. Control Bar (Start Button + Progress + Live Status)
        ctrl_frame = QFrame()
        ctrl_frame.setStyleSheet("background-color: #1F242B; border-radius: 8px; padding: 8px;")
        c_layout = QHBoxLayout(ctrl_frame)
        c_layout.setContentsMargins(12, 6, 12, 6)
        c_layout.setSpacing(12)

        self.btn_start = QPushButton("▶ START BATCH EVALUATION")
        self.btn_start.setFixedHeight(38)
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 13px;
                padding: 0 20px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #2EA043; }
            QPushButton:disabled { background-color: #30363D; color: #8B949E; }
        """)
        self.btn_start.clicked.connect(self._start_evaluation)
        c_layout.addWidget(self.btn_start)

        v_prog = QVBoxLayout()
        v_prog.setSpacing(4)
        self.prog_bar = QProgressBar()
        self.prog_bar.setFixedHeight(16)
        self.prog_bar.setTextVisible(True)
        self.prog_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #30363D;
                border-radius: 4px;
                text-align: center;
                background-color: #0D1117;
                color: #FFFFFF;
                font-size: 10px;
            }
            QProgressBar::chunk {
                background-color: #238636;
                border-radius: 3px;
            }
        """)
        v_prog.addWidget(self.prog_bar)

        self.lbl_status = QLabel("Ready. Select batch folder to start.")
        self.lbl_status.setStyleSheet("color: #8B949E; font-size: 11px;")
        v_prog.addWidget(self.lbl_status)
        c_layout.addLayout(v_prog, stretch=1)

        # Quick action buttons for results
        self.btn_open_excel = QPushButton("📊 Open Results Excel")
        self.btn_open_excel.setEnabled(False)
        self.btn_open_excel.setStyleSheet("background-color: #1F6FEB; color: white; padding: 7px 14px; border-radius: 4px; font-weight: bold;")
        self.btn_open_excel.clicked.connect(self._open_results_excel)
        c_layout.addWidget(self.btn_open_excel)

        self.btn_jump_review = QPushButton("🔍 Review Pallet")
        self.btn_jump_review.setEnabled(False)
        self.btn_jump_review.setStyleSheet("background-color: #D29922; color: #16191D; padding: 7px 14px; border-radius: 4px; font-weight: bold;")
        self.btn_jump_review.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        c_layout.addWidget(self.btn_jump_review)

        layout.addWidget(ctrl_frame)

        # 3. Live Batch Statistics Summary Bar
        self.stats_bar = QFrame()
        self.stats_bar.setStyleSheet("background-color: #16191D; border: 1px solid #30363D; border-radius: 6px; padding: 6px;")
        sb_layout = QHBoxLayout(self.stats_bar)
        sb_layout.setContentsMargins(12, 4, 12, 4)

        self.lbl_stat_total = QLabel("Total Scans: 0")
        self.lbl_stat_total.setStyleSheet("color: #58A6FF; font-weight: bold;")
        sb_layout.addWidget(self.lbl_stat_total)

        sb_layout.addWidget(QLabel("|"))

        self.lbl_stat_success = QLabel("Confirmed (Success): 0")
        self.lbl_stat_success.setStyleSheet("color: #3FB950; font-weight: bold;")
        sb_layout.addWidget(self.lbl_stat_success)

        sb_layout.addWidget(QLabel("|"))

        self.lbl_stat_review = QLabel("Review Needed: 0")
        self.lbl_stat_review.setStyleSheet("color: #D29922; font-weight: bold;")
        sb_layout.addWidget(self.lbl_stat_review)

        sb_layout.addWidget(QLabel("|"))

        self.lbl_stat_dups = QLabel("Duplicate HTs: 0")
        self.lbl_stat_dups.setStyleSheet("color: #F85149; font-weight: bold;")
        sb_layout.addWidget(self.lbl_stat_dups)

        sb_layout.addWidget(QLabel("|"))

        self.lbl_stat_avg = QLabel("Class Average: 0.00 Marks")
        self.lbl_stat_avg.setStyleSheet("color: #C9D1D9;")
        sb_layout.addWidget(self.lbl_stat_avg)

        sb_layout.addStretch()
        layout.addWidget(self.stats_bar)

        # 4. Results Table
        self.tbl_results = QTableWidget(0, 9)
        self.tbl_results.setHorizontalHeaderLabels([
            "Rank", "File Name", "Hall Ticket / Name", "Identification Type",
            "Total Marks", "Correct", "Wrong", "Confidence %", "Status"
        ])
        self.tbl_results.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tbl_results.horizontalHeader().setStretchLastSection(True)
        self.tbl_results.setStyleSheet("""
            QTableWidget {
                background-color: #0D1117;
                color: #C9D1D9;
                gridline-color: #21262D;
                border: 1px solid #30363D;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #161B22;
                color: #58A6FF;
                padding: 6px;
                border: 1px solid #21262D;
                font-weight: bold;
            }
            QTableWidget::item:selected {
                background-color: #1F6FEB;
                color: #FFFFFF;
            }
        """)
        layout.addWidget(self.tbl_results, stretch=1)

    def _build_review_pallet_tab(self):
        layout = QVBoxLayout(self.tab_review)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Splitter: Left is list of review-needed sheets, Right is the crop inspector and editor
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #30363D; }")

        # Left Panel: Review Queue List
        left_panel = QFrame()
        left_panel.setStyleSheet("background-color: #161B22; border: 1px solid #30363D; border-radius: 8px;")
        lp_layout = QVBoxLayout(left_panel)
        lp_layout.setContentsMargins(12, 12, 12, 12)
        lp_layout.setSpacing(8)

        lbl_queue = QLabel("📌 Sheets Pending Review")
        lbl_queue.setFont(QFont("Segoe UI", 11, QFont.Bold))
        lbl_queue.setStyleSheet("color: #E6EDF3;")
        lp_layout.addWidget(lbl_queue)

        self.list_reviews = QListWidget()
        self.list_reviews.setStyleSheet("""
            QListWidget {
                background-color: #0D1117;
                color: #C9D1D9;
                border: 1px solid #21262D;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #21262D;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #1F6FEB;
                color: #FFFFFF;
            }
            QListWidget::item:hover:!selected {
                background-color: #161B22;
            }
        """)
        self.list_reviews.currentRowChanged.connect(self._on_review_item_selected)
        lp_layout.addWidget(self.list_reviews, stretch=1)

        splitter.addWidget(left_panel)
        splitter.setStretchFactor(0, 1)

        # Right Panel: Image Crops & Correction Form
        right_panel = QFrame()
        right_panel.setStyleSheet("background-color: #161B22; border: 1px solid #30363D; border-radius: 8px;")
        rp_layout = QVBoxLayout(right_panel)
        rp_layout.setContentsMargins(14, 14, 14, 14)
        rp_layout.setSpacing(10)

        # Selected Sheet Header Banner
        self.lbl_review_header = QLabel("No Sheet Selected for Review")
        self.lbl_review_header.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.lbl_review_header.setStyleSheet("color: #58A6FF;")
        rp_layout.addWidget(self.lbl_review_header)

        # Warning / Conflict Reason Box
        self.box_conflict = QFrame()
        self.box_conflict.setStyleSheet("background-color: #381A1A; border: 1px solid #F85149; border-radius: 6px; padding: 6px;")
        bc_layout = QHBoxLayout(self.box_conflict)
        bc_layout.setContentsMargins(10, 6, 10, 6)
        self.lbl_conflict_reason = QLabel("Select a sheet from the queue to inspect.")
        self.lbl_conflict_reason.setStyleSheet("color: #FFA198; font-weight: bold; font-size: 11px;")
        bc_layout.addWidget(self.lbl_conflict_reason)
        rp_layout.addWidget(self.box_conflict)

        # Crops Display (Scrollable)
        crops_scroll = QScrollArea()
        crops_scroll.setWidgetResizable(True)
        crops_scroll.setStyleSheet("QScrollArea { border: 1px solid #30363D; background-color: #0D1117; border-radius: 6px; }")

        crops_container = QWidget()
        cc_layout = QVBoxLayout(crops_container)
        cc_layout.setContentsMargins(10, 10, 10, 10)
        cc_layout.setSpacing(12)

        # 1. Hall Ticket Crop
        cc_layout.addWidget(QLabel("🔍 Processed Hall Ticket Crop (2.5x Zoom + Red Dropout):"))
        self.lbl_ht_crop = QLabel("No image")
        self.lbl_ht_crop.setAlignment(Qt.AlignCenter)
        self.lbl_ht_crop.setStyleSheet("background-color: #000000; border: 1px dashed #30363D; min-height: 90px; border-radius: 4px;")
        cc_layout.addWidget(self.lbl_ht_crop)

        # 2. Candidate Name Crop
        cc_layout.addWidget(QLabel("🔍 Processed Candidate Name Crop (2.5x Zoom + Red Dropout):"))
        self.lbl_name_crop = QLabel("No image")
        self.lbl_name_crop.setAlignment(Qt.AlignCenter)
        self.lbl_name_crop.setStyleSheet("background-color: #000000; border: 1px dashed #30363D; min-height: 90px; border-radius: 4px;")
        cc_layout.addWidget(self.lbl_name_crop)

        crops_scroll.setWidget(crops_container)
        rp_layout.addWidget(crops_scroll, stretch=1)

        # Editable Correction Fields
        form_frame = QFrame()
        form_frame.setStyleSheet("background-color: #21262D; border: 1px solid #30363D; border-radius: 6px; padding: 10px;")
        f_grid = QGridLayout(form_frame)
        f_grid.setContentsMargins(10, 8, 10, 8)
        f_grid.setHorizontalSpacing(10)
        f_grid.setVerticalSpacing(8)

        f_grid.addWidget(QLabel("Corrected Hall Ticket No:"), 0, 0)
        self.edit_ht = QLineEdit()
        self.edit_ht.setFont(QFont("Consolas", 11, QFont.Bold))
        self.edit_ht.setStyleSheet("background-color: #0D1117; color: #58A6FF; border: 1px solid #30363D; padding: 6px; border-radius: 4px;")
        self.edit_ht.textChanged.connect(lambda t: self.edit_ht.setText(t.upper()))
        f_grid.addWidget(self.edit_ht, 0, 1)

        f_grid.addWidget(QLabel("Candidate Name:"), 1, 0)
        self.edit_name = QLineEdit()
        self.edit_name.setFont(QFont("Consolas", 11, QFont.Bold))
        self.edit_name.setStyleSheet("background-color: #0D1117; color: #58A6FF; border: 1px solid #30363D; padding: 6px; border-radius: 4px;")
        self.edit_name.textChanged.connect(lambda t: self.edit_name.setText(t.upper()))
        f_grid.addWidget(self.edit_name, 1, 1)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        self.btn_prev_review = QPushButton("⏮ Previous")
        self.btn_prev_review.setStyleSheet("background-color: #30363D; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_prev_review.clicked.connect(self._prev_review_sheet)
        btn_box.addWidget(self.btn_prev_review)

        self.btn_save_review = QPushButton("💾 CONFIRM & UPDATE EXCEL")
        self.btn_save_review.setStyleSheet("background-color: #238636; color: white; padding: 8px 24px; border-radius: 4px; font-weight: bold; font-size: 12px;")
        self.btn_save_review.clicked.connect(self._save_current_correction)
        btn_box.addWidget(self.btn_save_review, stretch=1)

        self.btn_next_review = QPushButton("Next ⏭")
        self.btn_next_review.setStyleSheet("background-color: #30363D; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_next_review.clicked.connect(self._next_review_sheet)
        btn_box.addWidget(self.btn_next_review)

        f_grid.addLayout(btn_box, 2, 0, 1, 2)

        rp_layout.addWidget(form_frame)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

    # --------------------------------------------------------------------------
    # File & Path Selection Logic (with Auto-detection & Missing Prompts)
    # --------------------------------------------------------------------------
    def _browse_batch_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Batch OMR Scans Folder")
        if not folder:
            return

        folder_path = Path(folder).resolve()
        self.batch_folder = folder_path
        self.txt_batch.setText(str(folder_path))

        # Default results output path
        default_out = folder_path / "OMR_Student_Identities.xlsx"
        self.txt_output.setText(str(default_out))

        # Auto-detect Key PDF
        pdf_files = list(folder_path.glob("*.pdf"))
        found_key = None
        for p in pdf_files:
            if not p.stem.startswith("debug_"):
                found_key = p
                break

        if found_key:
            self.txt_key.setText(str(found_key))
            self._on_key_loaded(found_key)
        else:
            self.txt_key.clear()

        # Auto-detect Student Roster
        roster_files = [
            f for f in folder_path.glob("*.xlsx")
            if not f.name.startswith("OMR_Student_Identities")
            and not f.name.startswith("~$")
        ]
        found_roster = None
        for r in roster_files:
            if "roster" in r.name.lower() or "student" in r.name.lower() or "nominal" in r.name.lower():
                found_roster = r
                break
        if not found_roster and roster_files:
            found_roster = roster_files[0]

        if found_roster:
            self.txt_roster.setText(str(found_roster))
        else:
            self.txt_roster.clear()

        # Check for missing files & display friendly banner
        missing_items = []
        if not found_key:
            missing_items.append("Answer Key (.pdf)")
            self.btn_banner_action1.setVisible(True)
        else:
            self.btn_banner_action1.setVisible(False)

        if not found_roster:
            missing_items.append("Student Roster (.xlsx)")
            self.btn_banner_action2.setVisible(True)
        else:
            self.btn_banner_action2.setVisible(False)

        if missing_items:
            self.banner_missing.setVisible(True)
            msg = f"⚠️ Note: {' and '.join(missing_items)} not detected in folder. Click below to select, or proceed without them."
            self.lbl_banner_msg.setText(msg)
        else:
            self.banner_missing.setVisible(False)

        # Count scanned images
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
        images = [
            f for f in folder_path.iterdir()
            if f.is_file() and f.suffix.lower() in image_exts
            and not f.stem.endswith("_processed")
            and not f.stem.endswith("_raw")
        ]
        self.lbl_status.setText(f"Found {len(images)} scanned OMR sheet images in '{folder_path.name}'. Ready to evaluate.")

    def _browse_key_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Answer Key PDF", str(self.batch_folder or ""), "PDF Files (*.pdf)")
        if f:
            self.txt_key.setText(f)
            self._on_key_loaded(Path(f))
            self._update_missing_banner()

    def _on_key_loaded(self, key_path: Path):
        """Inspects answer key question count to dynamically adapt UI spinbox controls."""
        try:
            from app.evaluation.answer_key import AnswerKeyExtractor
            extractor = AnswerKeyExtractor()
            k = extractor.extract_from_pdf(Path(key_path))
            n = len(k.items)
            if n >= 200:
                self.spn_to_q.setValue(200)
                self.spn_correct.setValue(1.00)
            elif n == 160:
                self.spn_to_q.setValue(160)
                self.spn_correct.setValue(0.50)
            elif n > 0:
                self.spn_to_q.setValue(n)
        except Exception:
            pass

    def _browse_roster_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Student Roster Excel", str(self.batch_folder or ""), "Excel Files (*.xlsx *.xls)")
        if f:
            self.txt_roster.setText(f)
            self._update_missing_banner()

    def _browse_output_excel(self):
        f, _ = QFileDialog.getSaveFileName(self, "Save Results Excel", str(self.txt_output.text() or ""), "Excel Files (*.xlsx)")
        if f:
            self.txt_output.setText(f)

    def _update_missing_banner(self):
        has_key = bool(self.txt_key.text().strip())
        has_roster = bool(self.txt_roster.text().strip())
        self.btn_banner_action1.setVisible(not has_key)
        self.btn_banner_action2.setVisible(not has_roster)
        if has_key and has_roster:
            self.banner_missing.setVisible(False)
        else:
            missing = []
            if not has_key: missing.append("Answer Key (.pdf)")
            if not has_roster: missing.append("Student Roster (.xlsx)")
            self.banner_missing.setVisible(True)
            self.lbl_banner_msg.setText(f"⚠️ Note: {' and '.join(missing)} not selected. Click below to choose or proceed.")

    def _update_license_ui(self):
        info = license_manager.get_status()
        if info["is_activated"]:
            self.btn_license.setText("🔑 Licensed Edition")
            self.btn_license.setStyleSheet("background-color: #1F382B; color: #3FB950; border: 1px solid #238636; padding: 4px 12px; border-radius: 4px; font-weight: bold;")
        elif info["status"] == "TRIAL":
            self.btn_license.setText(f"⏱️ Trial: {info['days_left']} Day(s) Left (Activate)")
            self.btn_license.setStyleSheet("background-color: #382E1A; color: #D29922; border: 1px solid #9E6A03; padding: 4px 12px; border-radius: 4px; font-weight: bold;")
        else:
            self.btn_license.setText("🔒 Trial Expired - Activate")
            self.btn_license.setStyleSheet("background-color: #381A1A; color: #F85149; border: 1px solid #DA3633; padding: 4px 12px; border-radius: 4px; font-weight: bold;")

    def _open_license_dialog(self, force_lock=False):
        dlg = LicenseDialog(self, force_lock=force_lock)
        dlg.exec()
        self._update_license_ui()

    # --------------------------------------------------------------------------
    # Evaluation Execution & Background Thread Handling
    # --------------------------------------------------------------------------
    def _start_evaluation(self):
        # Enforce 3-day trial and license verification
        lic = license_manager.get_status()
        if lic["status"] == "EXPIRED":
            self._open_license_dialog(force_lock=True)
            lic = license_manager.get_status()
            if lic["status"] == "EXPIRED":
                return

        folder_str = self.txt_batch.text().strip()
        if not folder_str:
            QMessageBox.warning(self, "Missing Folder", "Please select a Batch OMR Scans Folder first.")
            return

        folder = Path(folder_str)
        if not folder.exists() or not folder.is_dir():
            QMessageBox.critical(self, "Invalid Directory", f"Folder does not exist:\n{folder}")
            return

        out_str = self.txt_output.text().strip()
        out_path = Path(out_str) if out_str else None
        key_file = self.txt_key.text().strip() or None
        roster_file = self.txt_roster.text().strip() or None

        self.btn_start.setEnabled(False)
        self.prog_bar.setValue(0)
        self.lbl_status.setText("Initializing evaluation engine...")

        self.worker = BatchWorkerThread(
            target_folder=folder,
            output_excel=out_path,
            key_file=key_file,
            roster_file=roster_file,
            correct_mark=self.spn_correct.value(),
            wrong_mark=self.spn_wrong.value(),
            unattempted_mark=self.spn_unattempted.value(),
            from_question=self.spn_from_q.value(),
            to_question=self.spn_to_q.value(),
            reading_mode=self.cmb_reading_mode.currentData() or "auto"
        )
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _recalculate_marks(self):
        """Dynamically recalculates all student marks in-memory based on current marking controls."""
        if not self.results:
            self.lbl_status.setText("Marking scheme configured. Click '▶ START BATCH EVALUATION' to run.")
            return

        c_mark = self.spn_correct.value()
        w_mark = self.spn_wrong.value()
        u_mark = self.spn_unattempted.value()
        from_q = self.spn_from_q.value()
        to_q = self.spn_to_q.value()

        from app.evaluation.scoring_engine import ScoringEngine

        recalculated_count = 0
        for r in self.results:
            det_results = r.get("_detected_results")
            ans_key = r.get("_answer_key")
            tot_q = r.get("_total_questions", to_q)

            if det_results and ans_key:
                engine = ScoringEngine(
                    correct_mark=c_mark,
                    wrong_mark=w_mark,
                    unattempted_mark=u_mark,
                    total_questions=tot_q,
                    from_question=from_q,
                    to_question=to_q
                )
                _, corr_cnt, wrong_cnt, un_cnt, tot_marks, _, _ = engine.evaluate_sheet(det_results, ans_key)
                r["Correct"] = corr_cnt
                r["Correct Marks"] = round(corr_cnt * c_mark, 2)
                r["Wrong"] = wrong_cnt
                r["Wrong Marks"] = round(wrong_cnt * w_mark, 2)
                r["Unattempted"] = un_cnt
                r["Unattempted Marks"] = round(un_cnt * u_mark, 2)
                r["Total Marks"] = tot_marks
                recalculated_count += 1

        if recalculated_count > 0:
            rank_results(self.results, has_evaluation=True)
            self._populate_results_table(self.results)

            if self.excel_path and self.batch_folder:
                export_results_to_excel(
                    results=self.results,
                    output_excel=self.excel_path,
                    target_folder=self.batch_folder,
                    has_evaluation=True
                )
            self.lbl_status.setText(
                f"✅ Marks updated for {recalculated_count} sheets (Correct: {c_mark:+.2f}, Wrong: {w_mark:+.2f}, "
                f"No Resp: {u_mark:+.2f}, Q{from_q}..{to_q}). Excel file synced."
            )
        else:
            self.lbl_status.setText("No evaluated sheets available to update marks.")

    @Slot(int, int, str, str)
    def _on_worker_progress(self, cur, tot, fn, msg):
        pct = int((cur / max(tot, 1)) * 100)
        self.prog_bar.setValue(pct)
        self.lbl_status.setText(f"[{cur}/{tot}] {fn} ... {msg}")

    @Slot(bool, list, str, str)
    def _on_worker_finished(self, success, results, excel_path, err_msg):
        self.btn_start.setEnabled(True)
        if not success:
            self.lbl_status.setText(f"Evaluation finished with error: {err_msg}")
            QMessageBox.critical(self, "Batch Failed", f"Evaluation failed:\n{err_msg}")
            return

        self.results = results
        self.excel_path = Path(excel_path) if excel_path else None
        self.btn_open_excel.setEnabled(True)

        self.prog_bar.setValue(100)
        self.lbl_status.setText(f"Batch completed! Processed {len(results)} sheets. Results exported to Excel.")

        # Populate Results Table & Summary Badges
        self._populate_results_table(results)

        # Populate Review Pallet
        self._populate_review_pallet(results)

    def _populate_results_table(self, results: List[Dict[str, Any]]):
        self.tbl_results.setRowCount(0)
        self.tbl_results.setRowCount(len(results))

        success_cnt = sum(1 for r in results if r.get("Status") == "SUCCESS")
        verified_cnt = sum(1 for r in results if str(r.get("Status", "")).startswith("VERIFIED"))
        review_cnt = len(results) - success_cnt - verified_cnt
        dup_cnt = sum(1 for r in results if "Duplicate" in r.get("Status", ""))
        avg_marks = 0.0
        scores = [r.get("Total Marks") for r in results if isinstance(r.get("Total Marks"), (int, float))]
        if scores:
            avg_marks = sum(scores) / len(scores)

        self.lbl_stat_total.setText(f"Total Scans: {len(results)}")
        self.lbl_stat_success.setText(f"Confirmed (Success): {success_cnt + verified_cnt}")
        self.lbl_stat_review.setText(f"Review Needed: {review_cnt}")
        self.lbl_stat_dups.setText(f"Duplicate HTs: {dup_cnt}")
        self.lbl_stat_avg.setText(f"Class Average: {avg_marks:.2f} Marks")

        for row, r in enumerate(results):
            status = str(r.get("Status", ""))
            is_dup = "Duplicate" in status
            is_review = "REVIEW_REQUIRED" in status or "Low Confidence" in status

            items = [
                str(r.get("Rank", row + 1)),
                str(r.get("File Name", "")),
                str(r.get("Hall Ticket / Name", "")),
                str(r.get("Identification Type", "")),
                f"{r.get('Total Marks', 0.0):.2f}" if "Total Marks" in r else "-",
                str(r.get("Correct", "-")),
                str(r.get("Wrong", "-")),
                f"{r.get('Confidence %', 0.0)*100:.1f}%",
                status
            ]

            for col, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter if col not in (1, 2) else Qt.AlignLeft | Qt.AlignVCenter)

                if is_dup:
                    item.setBackground(QColor("#381A1A"))
                    if col == 8:
                        item.setForeground(QColor("#F85149"))
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)
                elif is_review:
                    item.setBackground(QColor("#2B2109"))
                    if col == 8:
                        item.setForeground(QColor("#D29922"))
                else:
                    item.setForeground(QColor("#C9D1D9"))

                self.tbl_results.setItem(row, col, item)

        self.tbl_results.resizeColumnsToContents()

    # --------------------------------------------------------------------------
    # Interactive Review Pallet Logic (Requirement 3)
    # --------------------------------------------------------------------------
    def _populate_review_pallet(self, results: List[Dict[str, Any]]):
        self.list_reviews.clear()
        self.review_records = [
            r for r in results 
            if r.get("Status") != "SUCCESS" and "VERIFIED" not in r.get("Status", "")
        ]

        count = len(self.review_records)
        self.tabs.setTabText(1, f"🔍 Review Pallet ({count} Pending)")
        self.btn_jump_review.setEnabled(count > 0)
        self.btn_jump_review.setText(f"🔍 Review Pallet ({count} pending)")

        if count == 0:
            self.lbl_review_header.setText("🎉 No Sheets Require Review! All HTs are Confirmed & Unique.")
            self.box_conflict.setVisible(False)
            self.lbl_ht_crop.setText("No pending reviews")
            self.lbl_name_crop.setText("No pending reviews")
            self.edit_ht.clear()
            self.edit_name.clear()
            return

        self.box_conflict.setVisible(True)
        for idx, r in enumerate(self.review_records, 1):
            fn = r.get("File Name", "")
            id_val = r.get("Hall Ticket / Name", "")
            status = r.get("Status", "")

            tag = "REVIEW"
            if "Duplicate" in status:
                tag = "⚠️ DUPLICATE HT"
            elif "Unregistered" in status or "Mismatch" in status:
                tag = "UNREGISTERED HT"
            elif "Assigned by Name" in status:
                tag = "ASSIGNED BY NAME"
            elif "Missing HT" in status:
                tag = "MISSING HT"
            elif "Low Confidence" in status:
                tag = "LOW CONF"
            elif "Blank" in status:
                tag = "BLANK"

            item_text = f"[{idx:02d}] {fn} | {tag}\n     {id_val}"
            item = QListWidgetItem(item_text)
            if "Duplicate" in status:
                item.setForeground(QColor("#F85149"))
            else:
                item.setForeground(QColor("#D29922"))
            self.list_reviews.addItem(item)

        # Select first item
        self.list_reviews.setCurrentRow(0)

    def _on_review_item_selected(self, row: int):
        if row < 0 or row >= len(self.review_records):
            return

        self.current_review_index = row
        record = self.review_records[row]
        fn = record.get("File Name", "")
        id_val = str(record.get("Hall Ticket / Name", ""))
        id_type = str(record.get("Identification Type", ""))
        status = str(record.get("Status", ""))

        self.lbl_review_header.setText(f"Reviewing: {fn}")
        self.lbl_conflict_reason.setText(f"Reason: {status}")

        # Set editable fields
        cand_name = record.get("Candidate Name", "") or record.get("_detected_name", "")
        if id_type.startswith("HALL TICKET"):
            self.edit_ht.setText(id_val)
            self.edit_name.setText(cand_name)
        else:
            self.edit_ht.setText("")
            self.edit_name.setText(id_val if not id_val.startswith("(") else cand_name)

        # Load processed crop images from processed_crops folder or target folder
        folder = self.batch_folder or Path(self.txt_batch.text().strip())
        stem = Path(fn).stem

        ht_crop_paths = [
            folder / "processed_crops" / f"{stem}_ht_processed.png",
            folder / f"{stem}_ht_processed.png"
        ]
        name_crop_paths = [
            folder / "processed_crops" / f"{stem}_name_processed.png",
            folder / f"{stem}_name_processed.png"
        ]

        ht_loaded = False
        for p in ht_crop_paths:
            if p.exists():
                pix = QPixmap(str(p))
                if not pix.isNull():
                    scaled = pix.scaledToWidth(580, Qt.SmoothTransformation)
                    self.lbl_ht_crop.setPixmap(scaled)
                    ht_loaded = True
                    break
        if not ht_loaded:
            self.lbl_ht_crop.setText(f"HT crop not found for {fn}")

        name_loaded = False
        for p in name_crop_paths:
            if p.exists():
                pix = QPixmap(str(p))
                if not pix.isNull():
                    scaled = pix.scaledToWidth(580, Qt.SmoothTransformation)
                    self.lbl_name_crop.setPixmap(scaled)
                    name_loaded = True
                    break
        if not name_loaded:
            self.lbl_name_crop.setText(f"Name crop not found for {fn}")

    def _save_current_correction(self):
        if self.current_review_index < 0 or self.current_review_index >= len(self.review_records):
            return

        record = self.review_records[self.current_review_index]
        new_ht = self.edit_ht.text().strip().upper()
        new_name = self.edit_name.text().strip().upper()

        if not new_ht and not new_name:
            QMessageBox.warning(self, "Empty Value", "Please enter either a Hall Ticket Number or Candidate Name.")
            return

        # Update record in results
        if new_ht:
            record["Hall Ticket / Name"] = new_ht
            record["Identification Type"] = "HALL TICKET"
        else:
            record["Hall Ticket / Name"] = new_name
            record["Identification Type"] = "CANDIDATE NAME (MISSING HT)"

        record["Status"] = "VERIFIED (Manual Review)"

        # Re-check duplicates across the batch
        detect_and_flag_duplicate_hall_tickets(self.results)

        # Update Excel spreadsheet file on disk
        self._sync_corrections_to_excel()

        # Refresh Results Table
        self._populate_results_table(self.results)

        # Refresh Review Queue
        curr_row = self.current_review_index
        self._populate_review_pallet(self.results)
        if curr_row < self.list_reviews.count():
            self.list_reviews.setCurrentRow(curr_row)

    def _sync_corrections_to_excel(self):
        """Immediately writes updated records to the generated Excel spreadsheet."""
        if not self.excel_path or not self.excel_path.exists():
            return

        try:
            wb = openpyxl.load_workbook(str(self.excel_path))
            ws = wb.active
            headers = [cell.value for cell in ws[1]]

            fn_col = headers.index("File Name") + 1 if "File Name" in headers else 2
            id_col = headers.index("Hall Ticket / Name") + 1 if "Hall Ticket / Name" in headers else 3
            type_col = headers.index("Identification Type") + 1 if "Identification Type" in headers else 4
            status_col = headers.index("Status") + 1 if "Status" in headers else len(headers)

            fill_verified = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")  # soft green
            font_verified = XlFont(name="Calibri", size=10, bold=True, color="375623")

            results_map = {r["File Name"]: r for r in self.results}

            for row in range(2, ws.max_row + 1):
                fname = ws.cell(row=row, column=fn_col).value
                if fname in results_map:
                    rec = results_map[fname]
                    ws.cell(row=row, column=id_col).value = rec["Hall Ticket / Name"]
                    ws.cell(row=row, column=type_col).value = rec["Identification Type"]
                    status_cell = ws.cell(row=row, column=status_col)
                    status_cell.value = rec["Status"]

                    if "VERIFIED" in rec["Status"]:
                        for col in range(1, len(headers) + 1):
                            ws.cell(row=row, column=col).fill = fill_verified
                        status_cell.font = font_verified

            wb.save(str(self.excel_path))
        except Exception as e:
            print(f"[ERROR] Could not sync correction to Excel: {e}")

    def _next_review_sheet(self):
        if self.list_reviews.count() == 0:
            return
        nxt = (self.list_reviews.currentRow() + 1) % self.list_reviews.count()
        self.list_reviews.setCurrentRow(nxt)

    def _prev_review_sheet(self):
        if self.list_reviews.count() == 0:
            return
        prv = (self.list_reviews.currentRow() - 1 + self.list_reviews.count()) % self.list_reviews.count()
        self.list_reviews.setCurrentRow(prv)

    def _open_results_excel(self):
        if self.excel_path and self.excel_path.exists():
            if sys.platform == "win32":
                os.startfile(str(self.excel_path))
            else:
                import subprocess
                subprocess.run(["xdg-open", str(self.excel_path)])

