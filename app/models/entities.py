"""Domain models and data entities for OMR evaluation."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any


@dataclass
class Examination:
    id: Optional[int] = None
    code: str = ""
    name: str = ""
    total_questions: int = 160
    correct_mark: float = 0.50
    wrong_mark: float = 0.00
    unattempted_mark: float = 0.00
    template_name: str = "OMR_AP_DSC_160_V1"
    status: str = "DRAFT"  # DRAFT, ACTIVE, COMPLETED, ARCHIVED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AnswerKeyItem:
    question_number: int
    correct_option: str  # A, B, C, D
    confidence: float = 1.0
    source_bbox: Optional[List[int]] = None


@dataclass
class AnswerKey:
    id: Optional[int] = None
    exam_id: int = 0
    version_number: int = 1
    version_hash: str = ""
    is_locked: bool = False
    source_file: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    items: Dict[int, str] = field(default_factory=dict)


@dataclass
class QuestionResult:
    question_number: int
    detected_option: str  # A, B, C, D, BLANK, MULTI, AMBIGUOUS
    correct_option: str
    classification: str   # CORRECT, WRONG, UNATTEMPTED, AMBIGUOUS, MULTI
    awarded_marks: float
    confidence: float
    fills: List[float] = field(default_factory=list)
    is_corrected: bool = False
    corrected_option: Optional[str] = None


@dataclass
class ProcessedSheet:
    id: Optional[int] = None
    exam_id: int = 0
    file_path: str = ""
    file_name: str = ""
    file_hash: str = ""
    hall_ticket_ocr: str = ""
    hall_ticket_final: str = ""
    candidate_name_ocr: str = ""
    candidate_name_final: str = ""
    status: str = "PENDING"  # SUCCESS, REVIEW_REQUIRED, REJECTED, PENDING
    review_reason: str = ""
    correct_count: int = 0
    wrong_count: int = 0
    unattempted_count: int = 0
    total_marks: float = 0.00
    student_rank: int = 0
    skew_angle: float = 0.0
    processed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    verified_at: Optional[str] = None
    responses: Dict[int, QuestionResult] = field(default_factory=dict)

    @property
    def display_identifier(self) -> str:
        """Returns Hall Ticket or candidate name fallback."""
        if self.hall_ticket_final and len(self.hall_ticket_final.strip()) >= 5:
            return self.hall_ticket_final.strip()
        if self.candidate_name_final and len(self.candidate_name_final.strip()) >= 3:
            return self.candidate_name_final.strip()
        return self.file_name


@dataclass
class AuditCorrection:
    id: Optional[int] = None
    sheet_id: int = 0
    field_type: str = ""  # QUESTION, HALL_TICKET, CANDIDATE_NAME
    target_index: Optional[int] = None  # question number or None
    old_value: str = ""
    new_value: str = ""
    reason: str = ""
    operator: str = "Operator"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

