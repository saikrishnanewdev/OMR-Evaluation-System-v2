"""OMR Form Template Definition and Geometric Grid Mapping."""
from dataclasses import dataclass
from typing import Tuple, Dict, List, Optional
from app.config.constants import (
    REF_CANVAS_WIDTH, REF_CANVAS_HEIGHT,
    TOTAL_QUESTIONS, QUESTIONS_PER_COLUMN, NUM_COLUMNS,
    COLUMN_BASE_X, OPTION_PITCH_X, ROW_BASE_Y, ROW_PITCH_Y,
    TOTAL_QUESTIONS_200, QUESTIONS_PER_COLUMN_200, NUM_COLUMNS_200,
    COLUMN_BASE_X_200, OPTION_PITCH_X_200, ROW_BASE_Y_200, ROW_PITCH_Y_200,
    TIMING_MARK_EXPECTED_COUNT, TIMING_MARK_EXPECTED_COUNT_200,
    BUBBLE_RADIUS, BUBBLE_CORE_RADIUS_RATIO,
    HT_FIELD_X_START, HT_FIELD_Y_START, HT_BOX_PITCH,
    HT_BOX_INNER_W, HT_BOX_INNER_H, HT_NUM_BOXES,
    NAME_FIELD_X_START, NAME_FIELD_X_END, NAME_FIELD_Y_START, NAME_FIELD_Y_END,
    HT_FIELD_X_START_200, HT_FIELD_X_END_200, HT_FIELD_Y_START_200, HT_FIELD_Y_END_200,
    NAME_FIELD_X_START_200, NAME_FIELD_X_END_200, NAME_FIELD_Y_START_200, NAME_FIELD_Y_END_200,
    OPTION_NAMES
)


@dataclass
class OMRTemplate:
    """Encapsulates calibrated coordinate rules for OMR forms (160Q standard or 200Q extended)."""

    name: str = "OMR_AP_DSC_160_V1"
    canvas_w: int = REF_CANVAS_WIDTH
    canvas_h: int = REF_CANVAS_HEIGHT
    total_questions: int = TOTAL_QUESTIONS
    questions_per_column: int = QUESTIONS_PER_COLUMN
    num_columns: int = NUM_COLUMNS
    column_base_x: Tuple[float, ...] = COLUMN_BASE_X
    option_pitch_x: float = OPTION_PITCH_X
    row_base_y: float = ROW_BASE_Y
    row_pitch_y: float = ROW_PITCH_Y
    options: Tuple[str, ...] = OPTION_NAMES
    timing_mark_expected_count: int = TIMING_MARK_EXPECTED_COUNT
    row_timing_start_idx: int = 0

    def get_bubble_center(
        self,
        question_number: int,
        option_index: int,
        timing_marks_left: Optional[List[Tuple[int, int, int, int]]] = None,
        timing_marks_right: Optional[List[Tuple[int, int, int, int]]] = None
    ) -> Tuple[float, float]:
        """
        Calculates center (x, y) for a given question and option index (0..3).
        Supports direct physical timing track projection when detected marks are provided,
        or standardized calibrated grid projection otherwise.
        """
        if not (1 <= question_number <= self.total_questions):
            raise ValueError(f"Question number out of range: {question_number} (expected 1..{self.total_questions})")
        if not (0 <= option_index < len(self.options)):
            raise ValueError(f"Option index out of range: {option_index}")

        col_idx = (question_number - 1) // self.questions_per_column
        row_idx = (question_number - 1) % self.questions_per_column

        base_x = self.column_base_x[col_idx]
        x = base_x + option_index * self.option_pitch_x

        # If physical timing tracks are provided for 200Q, both left and right tracks
        # are required for bilateral interpolation across the canvas. If only one track
        # is available or has missing marks, single-sided projection introduces severe
        # vertical tilt across columns; fall back to the calibrated standard grid instead.
        if (
            self.total_questions == 200
            and timing_marks_left is not None
            and timing_marks_right is not None
            and len(timing_marks_left) >= 56
            and len(timing_marks_right) >= 56
        ):
            ml = timing_marks_left[16 + row_idx]
            mr = timing_marks_right[16 + row_idx]
            yl = ml[1] + ml[3] / 2.0
            yr = mr[1] + mr[3] / 2.0
            weight = (base_x - 110.0) / (1578.0 - 110.0)
            y = yl + weight * (yr - yl)
            return x, y

        # Standard grid geometry with column skew compensation
        if self.total_questions == 160:
            skew_y = 0.0042 * (base_x - 274.0)
        else:
            skew_y = 0.0

        y = self.row_base_y + row_idx * self.row_pitch_y + skew_y
        return x, y

    def get_hall_ticket_box(self, box_index: int = 0) -> Tuple[int, int, int, int]:
        """
        Returns (x, y, w, h) for a character box in the Hall Ticket field.
        Supports both 160Q individual box indexing and 200Q full field bounds.
        """
        if self.total_questions == 200:
            w = HT_FIELD_X_END_200 - HT_FIELD_X_START_200
            h = HT_FIELD_Y_END_200 - HT_FIELD_Y_START_200
            return HT_FIELD_X_START_200, HT_FIELD_Y_START_200, w, h

        if not (0 <= box_index < HT_NUM_BOXES):
            raise ValueError(f"Hall ticket box index out of range: {box_index}")

        bx = int(HT_FIELD_X_START + box_index * HT_BOX_PITCH)
        by = int(HT_FIELD_Y_START)
        # Inner crop away from right and bottom grid lines
        return bx + 2, by + 2, HT_BOX_INNER_W, HT_BOX_INNER_H

    def get_candidate_name_box(self) -> Tuple[int, int, int, int]:
        """Returns (x, y, w, h) for the candidate name field."""
        if self.total_questions == 200:
            w = NAME_FIELD_X_END_200 - NAME_FIELD_X_START_200
            h = NAME_FIELD_Y_END_200 - NAME_FIELD_Y_START_200
            return NAME_FIELD_X_START_200, NAME_FIELD_Y_START_200, w, h

        w = NAME_FIELD_X_END - NAME_FIELD_X_START
        h = NAME_FIELD_Y_END - NAME_FIELD_Y_START
        return NAME_FIELD_X_START, NAME_FIELD_Y_START, w, h


# Standard 160-Question Template
template_160 = OMRTemplate(
    name="OMR_AP_DSC_160_V1",
    total_questions=TOTAL_QUESTIONS,
    questions_per_column=QUESTIONS_PER_COLUMN,
    num_columns=NUM_COLUMNS,
    column_base_x=COLUMN_BASE_X,
    option_pitch_x=OPTION_PITCH_X,
    row_base_y=ROW_BASE_Y,
    row_pitch_y=ROW_PITCH_Y,
    timing_mark_expected_count=TIMING_MARK_EXPECTED_COUNT,
    row_timing_start_idx=0
)

# Extended 200-Question Template (5 Columns x 40 Questions)
template_200 = OMRTemplate(
    name="OMR_200_EXTENDED_V1",
    total_questions=TOTAL_QUESTIONS_200,
    questions_per_column=QUESTIONS_PER_COLUMN_200,
    num_columns=NUM_COLUMNS_200,
    column_base_x=COLUMN_BASE_X_200,
    option_pitch_x=OPTION_PITCH_X_200,
    row_base_y=ROW_BASE_Y_200,
    row_pitch_y=ROW_PITCH_Y_200,
    timing_mark_expected_count=TIMING_MARK_EXPECTED_COUNT_200,
    row_timing_start_idx=16
)

# Global default standard template
standard_template = template_160


def get_template(total_questions: int = 160) -> OMRTemplate:
    """Returns appropriate template based on question count."""
    if total_questions >= 200:
        return template_200
    return template_160
