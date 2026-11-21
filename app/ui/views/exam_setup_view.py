"""Examination configuration view: scoring rules, form templates, and PDF answer key loading."""
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QSpinBox, QDoubleSpinBox, QComboBox, QPushButton, QFileDialog,
    QMessageBox, QFrame, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from app.models.entities import Examination
from app.database.repository import Repository, repository
from app.evaluation.answer_key import AnswerKeyExtractor
from app.config.constants import (
    TOTAL_QUESTIONS, DEFAULT_CORRECT_MARK,
    DEFAULT_WRONG_MARK, DEFAULT_UNATTEMPTED_MARK
)


class ExamSetupView(QWidget):
    """View to define examination parameters, mark schemes, and load reference answer keys."""

    examSelected = Signal(int)  # exam_id

    def __init__(self, repo: Repository = repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.current_exam: Examination = None
        self._setup_ui()
        self.refresh_exam_list()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(24)
        main_layout.setContentsMargins(24, 24, 24, 24)

        # Left Column: Existing Exams
        left_frame = QFrame()
        left_frame.setFixedWidth(280)
        left_frame.setStyleSheet("background-color: #252526; border-radius: 8px; padding: 12px;")
        left_layout = QVBoxLayout(left_frame)

        left_title = QLabel("Saved Examinations")
        left_title.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 14px;")
        left_layout.addWidget(left_title)

        self.exam_list = QListWidget()
        self.exam_list.setStyleSheet("""
            QListWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: 1px solid #3E3E42;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #2D2D30;
            }
            QListWidget::item:selected {
                background-color: #094771;
                color: #FFFFFF;
            }
        """)
        self.exam_list.itemClicked.connect(self._on_exam_selected)
        left_layout.addWidget(self.exam_list)

        self.btn_new = QPushButton("+ New Examination")
        self.btn_new.setStyleSheet("background-color: #0E639C; color: white; padding: 8px; border-radius: 4px;")
        self.btn_new.clicked.connect(self._reset_form)
        left_layout.addWidget(self.btn_new)

        main_layout.addWidget(left_frame)

        # Right Column: Setup Form
        right_frame = QFrame()
        right_frame.setStyleSheet("background-color: #252526; border-radius: 8px; padding: 20px;")
        form_layout = QVBoxLayout(right_frame)
        form_layout.setSpacing(16)

        form_title = QLabel("Examination Parameters & Scoring Configuration")
        form_title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        form_title.setStyleSheet("color: #FFFFFF;")
        form_layout.addWidget(form_title)

        grid = QGridLayout()
        grid.setSpacing(12)

        label_style = "color: #CCCCCC; font-size: 13px; font-weight: 500;"
        input_style = "background-color: #1E1E1E; color: #FFFFFF; border: 1px solid #3E3E42; border-radius: 4px; padding: 6px;"

        # Exam Code
        lbl_code = QLabel("Examination Code:")
        lbl_code.setStyleSheet(label_style)
        self.txt_code = QLineEdit("AP_DSC_SA08")
        self.txt_code.setStyleSheet(input_style)
        grid.addWidget(lbl_code, 0, 0)
        grid.addWidget(self.txt_code, 0, 1)

        # Exam Name
        lbl_name = QLabel("Examination Name:")
        lbl_name.setStyleSheet(label_style)
        self.txt_name = QLineEdit("AP DSC 2026 SA(Social) 3.0 Divisional Test-08")
        self.txt_name.setStyleSheet(input_style)
        grid.addWidget(lbl_name, 1, 0)
        grid.addWidget(self.txt_name, 1, 1)

        # Total Questions
        lbl_q_count = QLabel("Number of Questions:")
        lbl_q_count.setStyleSheet(label_style)
        self.spin_questions = QSpinBox()
        self.spin_questions.setRange(1, 300)
        self.spin_questions.setValue(TOTAL_QUESTIONS)
        self.spin_questions.setStyleSheet(input_style)
        grid.addWidget(lbl_q_count, 2, 0)
        grid.addWidget(self.spin_questions, 2, 1)

        # Marks for Correct
        lbl_correct = QLabel("Mark per Correct Answer (+):")
        lbl_correct.setStyleSheet(label_style)
        self.spin_correct = QDoubleSpinBox()
        self.spin_correct.setRange(0.0, 10.0)
        self.spin_correct.setSingleStep(0.25)
        self.spin_correct.setValue(DEFAULT_CORRECT_MARK)
        self.spin_correct.setStyleSheet(input_style)
        grid.addWidget(lbl_correct, 3, 0)
        grid.addWidget(self.spin_correct, 3, 1)

        # Negative Marks for Wrong
        lbl_wrong = QLabel("Mark deduction per Wrong Answer (-):")
        lbl_wrong.setStyleSheet(label_style)
        self.spin_wrong = QDoubleSpinBox()
        self.spin_wrong.setRange(0.0, 5.0)
        self.spin_wrong.setSingleStep(0.25)
        self.spin_wrong.setValue(DEFAULT_WRONG_MARK)
        self.spin_wrong.setStyleSheet(input_style)
        grid.addWidget(lbl_wrong, 4, 0)
        grid.addWidget(self.spin_wrong, 4, 1)

        # Unattempted Marks
        lbl_unattempted = QLabel("Mark per Unattempted Question:")
        lbl_unattempted.setStyleSheet(label_style)
        self.spin_unattempted = QDoubleSpinBox()
        self.spin_unattempted.setRange(0.0, 5.0)
        self.spin_unattempted.setValue(DEFAULT_UNATTEMPTED_MARK)
        self.spin_unattempted.setStyleSheet(input_style)
        grid.addWidget(lbl_unattempted, 5, 0)
        grid.addWidget(self.spin_unattempted, 5, 1)

        # Form Template
        lbl_template = QLabel("OMR Sheet Form Template:")
        lbl_template.setStyleSheet(label_style)
        self.combo_template = QComboBox()
        self.combo_template.addItems(["OMR_AP_DSC_160_V1 (160 Questions, Red Dropout)"])
        self.combo_template.setStyleSheet(input_style)
        grid.addWidget(lbl_template, 6, 0)
        grid.addWidget(self.combo_template, 6, 1)

        form_layout.addLayout(grid)

        # Answer Key PDF Section
        key_box = QFrame()
        key_box.setStyleSheet("background-color: #1E1E1E; border: 1px dashed #0E639C; border-radius: 6px; padding: 14px;")
        key_layout = QVBoxLayout(key_box)

        key_title = QLabel("Reference Answer-Key Document (PDF)")
        key_title.setStyleSheet("color: #FFFFFF; font-weight: bold;")
        key_layout.addWidget(key_title)

        key_row = QHBoxLayout()
        self.txt_pdf_path = QLineEdit("SA-08.pdf")
        self.txt_pdf_path.setStyleSheet(input_style)
        self.btn_browse_pdf = QPushButton("Browse PDF...")
        self.btn_browse_pdf.setStyleSheet("background-color: #3E3E42; color: white; padding: 6px 12px; border-radius: 4px;")
        self.btn_browse_pdf.clicked.connect(self._browse_pdf)

        self.btn_extract_key = QPushButton("Extract & Validate PDF Key")
        self.btn_extract_key.setStyleSheet("background-color: #107C41; color: white; padding: 6px 14px; border-radius: 4px; font-weight: bold;")
        self.btn_extract_key.clicked.connect(self._extract_key)

        key_row.addWidget(self.txt_pdf_path)
        key_row.addWidget(self.btn_browse_pdf)
        key_row.addWidget(self.btn_extract_key)
        key_layout.addLayout(key_row)

        self.lbl_key_status = QLabel("Answer Key Status: Not imported yet.")
        self.lbl_key_status.setStyleSheet("color: #D83B01; font-size: 12px;")
        key_layout.addWidget(self.lbl_key_status)

        form_layout.addWidget(key_box)

        # Save Button
        btn_save = QPushButton("Save & Activate Examination")
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #0E639C;
                color: #FFFFFF;
                font-size: 14px;
                font-weight: bold;
                padding: 12px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #1177BB; }
        """)
        btn_save.clicked.connect(self._save_examination)
        form_layout.addWidget(btn_save)

        form_layout.addStretch()
        main_layout.addWidget(right_frame)

    def refresh_exam_list(self) -> None:
        """Reloads exams from SQLite."""
        self.exam_list.clear()
        exams = self.repo.list_examinations()
        for ex in exams:
            item = QListWidgetItem(f"{ex.code} - {ex.name}")
            item.setData(Qt.UserRole, ex.id)
            self.exam_list.addItem(item)
            if self.current_exam and ex.id == self.current_exam.id:
                self.exam_list.setCurrentItem(item)

    def _on_exam_selected(self, item: QListWidgetItem) -> None:
        exam_id = item.data(Qt.UserRole)
        exam = self.repo.get_examination(exam_id)
        if exam:
            self.current_exam = exam
            self.txt_code.setText(exam.code)
            self.txt_name.setText(exam.name)
            self.spin_questions.setValue(exam.total_questions)
            self.spin_correct.setValue(exam.correct_mark)
            self.spin_wrong.setValue(exam.wrong_mark)
            self.spin_unattempted.setValue(exam.unattempted_mark)

            # Check if answer key is loaded
            key = self.repo.get_latest_answer_key(exam.id)
            if key:
                self.lbl_key_status.setText(f"Answer Key Status: Loaded ({len(key.items)} questions, Hash: {key.version_hash[:10]}...)")
                self.lbl_key_status.setStyleSheet("color: #107C41; font-weight: bold;")
            else:
                self.lbl_key_status.setText("Answer Key Status: Not imported yet.")
                self.lbl_key_status.setStyleSheet("color: #D83B01;")

            self.examSelected.emit(exam.id)

    def _reset_form(self) -> None:
        self.current_exam = None
        self.txt_code.setText("NEW_EXAM_01")
        self.txt_name.setText("New Examination")
        self.spin_questions.setValue(TOTAL_QUESTIONS)
        self.spin_correct.setValue(DEFAULT_CORRECT_MARK)
        self.spin_wrong.setValue(DEFAULT_WRONG_MARK)
        self.spin_unattempted.setValue(DEFAULT_UNATTEMPTED_MARK)
        self.lbl_key_status.setText("Answer Key Status: Not imported yet.")
        self.lbl_key_status.setStyleSheet("color: #D83B01;")

    def _browse_pdf(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Answer Key PDF", "", "PDF Files (*.pdf)")
        if file_path:
            self.txt_pdf_path.setText(file_path)

    def _extract_key(self) -> None:
        pdf_path = Path(self.txt_pdf_path.text().strip())
        if not pdf_path.exists():
            QMessageBox.critical(self, "File Not Found", f"Cannot find PDF file: {pdf_path}")
            return

        try:
            extractor = AnswerKeyExtractor()
            key = extractor.extract_from_pdf(pdf_path)
            errors = AnswerKeyExtractor.validate_key(key.items, expected_count=self.spin_questions.value())
            if errors:
                QMessageBox.warning(self, "Key Validation Warnings", "\n".join(errors[:5]))
            else:
                self.lbl_key_status.setText(f"Answer Key Status: Successfully Extracted ({len(key.items)} items, Hash: {key.version_hash[:10]}...)")
                self.lbl_key_status.setStyleSheet("color: #107C41; font-weight: bold;")
                self._temp_key = key
                QMessageBox.information(self, "Extraction Complete", f"Successfully extracted {len(key.items)} answers from {pdf_path.name}.")
        except Exception as e:
            QMessageBox.critical(self, "Extraction Error", f"Failed to extract answer key: {e}")

    def _save_examination(self) -> None:
        code = self.txt_code.text().strip()
        name = self.txt_name.text().strip()
        if not code or not name:
            QMessageBox.warning(self, "Missing Fields", "Please enter both Examination Code and Examination Name.")
            return

        exam = Examination(
            id=self.current_exam.id if self.current_exam else None,
            code=code,
            name=name,
            total_questions=self.spin_questions.value(),
            correct_mark=self.spin_correct.value(),
            wrong_mark=self.spin_wrong.value(),
            unattempted_mark=self.spin_unattempted.value(),
            template_name="OMR_AP_DSC_160_V1",
            status="ACTIVE"
        )

        try:
            if exam.id:
                # Update logic
                pass
            else:
                existing = self.repo.get_examination_by_code(code)
                if existing:
                    exam.id = existing.id
                else:
                    exam.id = self.repo.create_examination(exam)

            self.current_exam = exam

            # Save extracted answer key if present
            if hasattr(self, "_temp_key") and self._temp_key:
                self._temp_key.exam_id = exam.id
                self.repo.save_answer_key(self._temp_key)

            self.refresh_exam_list()
            self.examSelected.emit(exam.id)
            QMessageBox.information(self, "Saved", f"Examination '{name}' ({code}) saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to save examination: {e}")

