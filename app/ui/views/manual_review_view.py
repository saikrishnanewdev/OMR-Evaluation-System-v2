"""Manual review workspace with dual image canvas, interactive overlays, and audited corrections."""
from pathlib import Path
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QLineEdit, QMessageBox, QFrame, QHeaderView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from app.models.entities import ProcessedSheet, Examination, QuestionResult
from app.database.repository import Repository, repository
from app.services.evaluation_service import EvaluationService, evaluation_service
from app.omr.preprocessor import Preprocessor
from app.omr.template import OMRTemplate, standard_template
from app.ui.widgets.image_viewer import ImageViewer
from app.config.constants import (
    HT_FIELD_X_START, HT_FIELD_Y_START, HT_FIELD_X_END, HT_FIELD_Y_END,
    BUBBLE_RADIUS
)


class ManualReviewView(QWidget):
    """Interactive manual review workspace for auditing student credentials and bubble marks."""

    sheetVerified = Signal(int)

    def __init__(
        self,
        repo: Repository = repository,
        service: EvaluationService = evaluation_service,
        parent=None
    ):
        super().__init__(parent)
        self.repo = repo
        self.service = service
        self.template = standard_template
        self.current_exam: Optional[Examination] = None
        self.current_sheet: Optional[ProcessedSheet] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Top Control Bar
        top_bar = QFrame()
        top_bar.setStyleSheet("background-color: #252526; border-radius: 6px; padding: 10px;")
        bar_layout = QHBoxLayout(top_bar)

        lbl_select = QLabel("Select Sheet:")
        lbl_select.setStyleSheet("color: #FFFFFF; font-weight: bold;")
        self.combo_sheets = QComboBox()
        self.combo_sheets.setMinimumWidth(350)
        self.combo_sheets.setStyleSheet("background-color: #1E1E1E; color: white; padding: 6px; border: 1px solid #3E3E42;")
        self.combo_sheets.currentIndexChanged.connect(self._on_sheet_selected)

        self.btn_refresh = QPushButton("Refresh Queue")
        self.btn_refresh.setStyleSheet("background-color: #3E3E42; color: white; padding: 6px 14px; border-radius: 4px;")
        self.btn_refresh.clicked.connect(self.reload_sheets)

        self.lbl_status_badge = QLabel("Status: NONE")
        self.lbl_status_badge.setStyleSheet("font-weight: bold; padding: 4px 8px; border-radius: 4px;")

        bar_layout.addWidget(lbl_select)
        bar_layout.addWidget(self.combo_sheets)
        bar_layout.addWidget(self.btn_refresh)
        bar_layout.addWidget(self.lbl_status_badge)
        bar_layout.addStretch()

        # Canvas tools
        self.btn_fit = QPushButton("Fit to Window")
        self.btn_fit.setStyleSheet("background-color: #0E639C; color: white; padding: 6px 12px; border-radius: 4px;")
        self.btn_fit.clicked.connect(lambda: self.viewer.reset_view())
        bar_layout.addWidget(self.btn_fit)

        layout.addWidget(top_bar)

        # Main Splitter: Left = ImageViewer, Right = Details & Responses
        splitter = QSplitter(Qt.Horizontal)

        # Left: Interactive Canvas
        self.viewer = ImageViewer()
        splitter.addWidget(self.viewer)

        # Right: Tabular responses and correction panel
        right_panel = QFrame()
        right_panel.setStyleSheet("background-color: #252526; border-radius: 6px;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)

        # Candidate Details Box
        cand_box = QFrame()
        cand_box.setStyleSheet("background-color: #1E1E1E; border: 1px solid #3E3E42; border-radius: 6px; padding: 10px;")
        cand_layout = QVBoxLayout(cand_box)

        lbl_cand_title = QLabel("Candidate Identification & Verification")
        lbl_cand_title.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 13px;")
        cand_layout.addWidget(lbl_cand_title)

        ht_row = QHBoxLayout()
        ht_lbl = QLabel("Hall Ticket:")
        ht_lbl.setStyleSheet("color: #CCCCCC; width: 80px;")
        self.txt_ht = QLineEdit()
        self.txt_ht.setStyleSheet("background-color: #2D2D30; color: white; border: 1px solid #3E3E42; padding: 4px;")
        self.btn_save_ht = QPushButton("Update HT")
        self.btn_save_ht.setStyleSheet("background-color: #0E639C; color: white; padding: 4px 10px; border-radius: 3px;")
        self.btn_save_ht.clicked.connect(self._update_hall_ticket)
        ht_row.addWidget(ht_lbl)
        ht_row.addWidget(self.txt_ht)
        ht_row.addWidget(self.btn_save_ht)
        cand_layout.addLayout(ht_row)

        name_row = QHBoxLayout()
        name_lbl = QLabel("Candidate Name:")
        name_lbl.setStyleSheet("color: #CCCCCC; width: 80px;")
        self.txt_name = QLineEdit()
        self.txt_name.setStyleSheet("background-color: #2D2D30; color: white; border: 1px solid #3E3E42; padding: 4px;")
        self.btn_save_name = QPushButton("Update Name")
        self.btn_save_name.setStyleSheet("background-color: #0E639C; color: white; padding: 4px 10px; border-radius: 3px;")
        self.btn_save_name.clicked.connect(self._update_candidate_name)
        name_row.addWidget(name_lbl)
        name_row.addWidget(self.txt_name)
        name_row.addWidget(self.btn_save_name)
        cand_layout.addLayout(name_row)

        right_layout.addWidget(cand_box)

        # Score Summary
        self.lbl_scores = QLabel("Correct: 0 | Wrong: 0 | Unattempted: 0 | Total Marks: 0.00 | Rank: -")
        self.lbl_scores.setStyleSheet("color: #00B294; font-weight: bold; font-size: 13px; padding: 4px;")
        right_layout.addWidget(self.lbl_scores)

        # Question Responses Table
        self.resp_table = QTableWidget(0, 5)
        self.resp_table.setHorizontalHeaderLabels(["Q#", "Detected", "Correct", "Status", "Confidence"])
        self.resp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.resp_table.setStyleSheet("""
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
                padding: 4px;
            }
        """)
        self.resp_table.itemSelectionChanged.connect(self._on_question_selected)
        right_layout.addWidget(self.resp_table)

        # Quick Question Correction Box
        corr_box = QFrame()
        corr_box.setStyleSheet("background-color: #1E1E1E; border: 1px solid #3E3E42; border-radius: 6px; padding: 10px;")
        corr_layout = QHBoxLayout(corr_box)

        lbl_corr_q = QLabel("Question:")
        lbl_corr_q.setStyleSheet("color: white;")
        self.combo_q = QComboBox()
        self.combo_q.addItems([str(i) for i in range(1, 161)])
        self.combo_q.setStyleSheet("background-color: #2D2D30; color: white;")

        lbl_corr_opt = QLabel("Set Answer:")
        lbl_corr_opt.setStyleSheet("color: white;")
        self.combo_opt = QComboBox()
        self.combo_opt.addItems(["A", "B", "C", "D", "BLANK"])
        self.combo_opt.setStyleSheet("background-color: #2D2D30; color: white;")

        self.btn_apply_corr = QPushButton("Apply Correction & Recalculate")
        self.btn_apply_corr.setStyleSheet("background-color: #107C41; color: white; padding: 6px 14px; font-weight: bold; border-radius: 4px;")
        self.btn_apply_corr.clicked.connect(self._apply_question_correction)

        corr_layout.addWidget(lbl_corr_q)
        corr_layout.addWidget(self.combo_q)
        corr_layout.addWidget(lbl_corr_opt)
        corr_layout.addWidget(self.combo_opt)
        corr_layout.addWidget(self.btn_apply_corr)
        corr_layout.addStretch()

        right_layout.addWidget(corr_box)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)

        layout.addWidget(splitter)

    def set_context(self, exam_id: int) -> None:
        self.current_exam = self.repo.get_examination(exam_id)
        self.reload_sheets()

    def reload_sheets(self) -> None:
        if not self.current_exam:
            return
        self.combo_sheets.clear()
        sheets = self.repo.list_sheets(self.current_exam.id)
        for s in sheets:
            badge = f"[{s.status}]"
            name = s.display_identifier
            self.combo_sheets.addItem(f"{badge} {name} ({s.file_name})", s.id)

    def _on_sheet_selected(self, index: int) -> None:
        sheet_id = self.combo_sheets.currentData()
        if not sheet_id:
            return
        sheet = self.repo.get_sheet(sheet_id)
        if not sheet:
            return

        self.current_sheet = sheet
        self.txt_ht.setText(sheet.hall_ticket_final)
        self.txt_name.setText(sheet.candidate_name_final)

        # Update badge
        status_colors = {
            "SUCCESS": ("#107C41", "#FFFFFF"),
            "REVIEW_REQUIRED": ("#D83B01", "#FFFFFF"),
            "VERIFIED": ("#008272", "#FFFFFF"),
            "REJECTED": ("#E81123", "#FFFFFF")
        }
        bg, fg = status_colors.get(sheet.status, ("#3E3E42", "#FFFFFF"))
        self.lbl_status_badge.setText(f"Status: {sheet.status}")
        self.lbl_status_badge.setStyleSheet(f"background-color: {bg}; color: {fg}; font-weight: bold; padding: 4px 8px; border-radius: 4px;")

        self.lbl_scores.setText(
            f"Correct: {sheet.correct_count} | Wrong: {sheet.wrong_count} | "
            f"Unattempted: {sheet.unattempted_count} | Total Marks: {sheet.total_marks:.2f} | Rank: {sheet.student_rank}"
        )

        # Load image on canvas with overlays
        self._load_sheet_canvas(sheet)

        # Populate responses table
        self._populate_responses_table(sheet)

    def _load_sheet_canvas(self, sheet: ProcessedSheet) -> None:
        file_path = Path(sheet.file_path)
        if not file_path.exists():
            return

        try:
            raw_img = Preprocessor.load_image(file_path)
            aligned_img, _ = Preprocessor.align_and_deskew(raw_img)
            self.viewer.set_cv_image(aligned_img)

            # Add overlays
            # 1. Identification Box highlight
            self.viewer.highlight_box(
                HT_FIELD_X_START, HT_FIELD_Y_START - 5,
                HT_FIELD_X_END - HT_FIELD_X_START, HT_FIELD_Y_END - HT_FIELD_Y_START + 10,
                "#FFCC00"
            )

            # 2. Bubble Overlays
            opt_map = {"A": 0, "B": 1, "C": 2, "D": 3}
            for q_num, resp in sheet.responses.items():
                if resp.detected_option in opt_map:
                    opt_idx = opt_map[resp.detected_option]
                    cx, cy = self.template.get_bubble_center(q_num, opt_idx)
                    color = "#107C41" if resp.classification == "CORRECT" else "#E81123"
                    self.viewer.add_bubble_overlay(cx, cy, BUBBLE_RADIUS, color, f"Q{q_num}: {resp.detected_option}")
                elif resp.classification in ("MULTI", "AMBIGUOUS"):
                    for opt_idx in range(4):
                        cx, cy = self.template.get_bubble_center(q_num, opt_idx)
                        self.viewer.add_bubble_overlay(cx, cy, BUBBLE_RADIUS, "#D83B01", f"Q{q_num}: {resp.classification}")
        except Exception as e:
            print(f"Error rendering canvas overlays: {e}")

    def _populate_responses_table(self, sheet: ProcessedSheet) -> None:
        self.resp_table.setRowCount(len(sheet.responses))
        for row_idx, (q_num, resp) in enumerate(sorted(sheet.responses.items())):
            c_q = QTableWidgetItem(str(q_num))
            c_q.setTextAlignment(Qt.AlignCenter)

            c_det = QTableWidgetItem(resp.detected_option + (" *" if resp.is_corrected else ""))
            c_det.setTextAlignment(Qt.AlignCenter)

            c_ans = QTableWidgetItem(resp.correct_option)
            c_ans.setTextAlignment(Qt.AlignCenter)

            c_stat = QTableWidgetItem(resp.classification)
            c_stat.setTextAlignment(Qt.AlignCenter)
            if resp.classification == "CORRECT":
                c_stat.setForeground(QColor(16, 124, 65))
            elif resp.classification == "WRONG":
                c_stat.setForeground(QColor(232, 17, 35))
            else:
                c_stat.setForeground(QColor(216, 59, 1))

            c_conf = QTableWidgetItem(f"{resp.confidence:.2f}")
            c_conf.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.resp_table.setItem(row_idx, 0, c_q)
            self.resp_table.setItem(row_idx, 1, c_det)
            self.resp_table.setItem(row_idx, 2, c_ans)
            self.resp_table.setItem(row_idx, 3, c_stat)
            self.resp_table.setItem(row_idx, 4, c_conf)

    def _on_question_selected(self) -> None:
        sel_items = self.resp_table.selectedItems()
        if sel_items:
            row = sel_items[0].row()
            q_num_item = self.resp_table.item(row, 0)
            if q_num_item:
                q_num = int(q_num_item.text())
                self.combo_q.setCurrentText(str(q_num))

    def _update_hall_ticket(self) -> None:
        if not self.current_sheet or not self.current_exam:
            return
        new_ht = self.txt_ht.text().strip().upper()
        if not new_ht:
            return
        self.service.apply_manual_correction(
            self.current_exam, self.current_sheet.id, "HALL_TICKET", new_ht,
            reason="Operator manual correction of Hall Ticket"
        )
        self.sheetVerified.emit(self.current_sheet.id)
        QMessageBox.information(self, "Updated", f"Hall Ticket updated to '{new_ht}'.")

    def _update_candidate_name(self) -> None:
        if not self.current_sheet or not self.current_exam:
            return
        new_name = self.txt_name.text().strip().upper()
        self.service.apply_manual_correction(
            self.current_exam, self.current_sheet.id, "CANDIDATE_NAME", new_name,
            reason="Operator manual correction of Candidate Name"
        )
        self.sheetVerified.emit(self.current_sheet.id)
        QMessageBox.information(self, "Updated", f"Candidate Name updated to '{new_name}'.")

    def _apply_question_correction(self) -> None:
        if not self.current_sheet or not self.current_exam:
            return
        q_num = int(self.combo_q.currentText())
        new_opt = self.combo_opt.currentText()

        updated_sheet = self.service.apply_manual_correction(
            self.current_exam, self.current_sheet.id, "QUESTION", new_opt,
            target_index=q_num, reason=f"Operator corrected Q{q_num} to {new_opt}"
        )
        self.current_sheet = updated_sheet
        self._on_sheet_selected(0)
        self.sheetVerified.emit(updated_sheet.id)
        QMessageBox.information(self, "Correction Applied", f"Question {q_num} updated to {new_opt}. Score recalculated: {updated_sheet.total_marks:.2f} marks.")

