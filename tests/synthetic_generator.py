"""Synthetic OMR answer sheet generator for automated edge-case testing."""
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from app.config.constants import (
    REF_CANVAS_WIDTH, REF_CANVAS_HEIGHT, TOTAL_QUESTIONS,
    BUBBLE_RADIUS, COLUMN_BASE_X, OPTION_PITCH_X, ROW_BASE_Y, ROW_PITCH_Y,
    QUESTIONS_PER_COLUMN, OPTION_NAMES, HT_FIELD_X_START, HT_FIELD_Y_START,
    HT_BOX_PITCH, HT_NUM_BOXES, HT_BOX_INNER_W, HT_BOX_INNER_H
)


class SyntheticOMRGenerator:
    """Generates synthetic OMR sheets based on the calibrated standard template."""

    def __init__(self, base_image_path: Optional[Path] = None):
        if base_image_path and Path(base_image_path).exists():
            self.base_image = cv2.imread(str(base_image_path))
        else:
            self.base_image = self._create_blank_canvas()

    def _create_blank_canvas(self) -> np.ndarray:
        """Draws a synthetic blank form with timing tracks and printed red bubbles."""
        img = np.full((REF_CANVAS_HEIGHT, REF_CANVAS_WIDTH, 3), 245, dtype=np.uint8)

        # Draw 49 left and right black timing marks matching calibrated master fiducials
        from app.omr.preprocessor import REF_TIMING_POINTS
        for pt in REF_TIMING_POINTS:
            cx, cy = pt
            x1, y1 = int(round(cx - 24)), int(round(cy - 9))
            cv2.rectangle(img, (x1, y1), (x1 + 48, y1 + 18), (20, 20, 20), -1)

        # Draw 16 Hall Ticket boxes (in red/orange)
        for i in range(HT_NUM_BOXES):
            bx = int(HT_FIELD_X_START + i * HT_BOX_PITCH)
            by = int(HT_FIELD_Y_START)
            cv2.rectangle(img, (bx, by), (bx + int(HT_BOX_PITCH), by + 36), (40, 40, 230), 2)

        # Draw 160 questions (4 columns x 40 rows) with 4 red bubble outlines each
        for col_idx in range(4):
            base_x = COLUMN_BASE_X[col_idx]
            for row_idx in range(QUESTIONS_PER_COLUMN):
                y = int(ROW_BASE_Y + row_idx * ROW_PITCH_Y)
                for opt_idx in range(4):
                    x = int(base_x + opt_idx * OPTION_PITCH_X)
                    # Draw red circular outline (dropout ink)
                    cv2.circle(img, (x, y), BUBBLE_RADIUS, (40, 40, 230), 2)

        return img

    def generate_sheet(
        self,
        answers: Dict[int, str],
        hall_ticket: str = "KNL2025SATS00001",
        candidate_name: str = "CANDIDATE",
        rotation_deg: float = 0.0,
        faint_indices: Optional[List[int]] = None,
        multi_indices: Optional[List[int]] = None,
        partial_indices: Optional[List[int]] = None
    ) -> np.ndarray:
        """
        Renders candidate responses onto the sheet.
        answers: {question_number: 'A'|'B'|'C'|'D'|'BLANK'}
        """
        sheet = self.base_image.copy()
        faint_set = set(faint_indices or [])
        multi_set = set(multi_indices or [])
        partial_set = set(partial_indices or [])
        opt_map = {"A": 0, "B": 1, "C": 2, "D": 3}

        # 1. Fill bubbles
        for q_num in range(1, TOTAL_QUESTIONS + 1):
            opt_str = answers.get(q_num, "BLANK")
            col_idx = (q_num - 1) // QUESTIONS_PER_COLUMN
            row_idx = (q_num - 1) % QUESTIONS_PER_COLUMN
            base_x = COLUMN_BASE_X[col_idx]
            y = int(ROW_BASE_Y + row_idx * ROW_PITCH_Y)

            # Check if multi-marked
            if q_num in multi_set:
                for opt_idx in [0, 1]:  # fill both A and B
                    x = int(base_x + opt_idx * OPTION_PITCH_X)
                    cv2.circle(sheet, (x, y), BUBBLE_RADIUS - 2, (30, 30, 30), -1)
                continue

            if opt_str in opt_map:
                opt_idx = opt_map[opt_str]
                x = int(base_x + opt_idx * OPTION_PITCH_X)

                if q_num in faint_set:
                    # Faint pencil fill: medium gray
                    cv2.circle(sheet, (x, y), BUBBLE_RADIUS - 3, (145, 145, 145), -1)
                elif q_num in partial_set:
                    # Partial fill: only a crescent or dot
                    cv2.ellipse(sheet, (x, y), (BUBBLE_RADIUS - 2, 4), 30, 0, 360, (30, 30, 30), -1)
                else:
                    # Solid dark black/blue ballpoint pen
                    cv2.circle(sheet, (x, y), BUBBLE_RADIUS - 2, (30, 30, 30), -1)

        # 2. Draw Hall ticket characters (dark black font)
        if hall_ticket:
            for i, ch in enumerate(hall_ticket[:HT_NUM_BOXES]):
                bx = int(HT_FIELD_X_START + i * HT_BOX_PITCH) + 8
                by = int(HT_FIELD_Y_START) + 26
                cv2.putText(sheet, ch, (bx, by), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (20, 20, 20), 2)

        # 3. Apply rotation / skew if requested
        if abs(rotation_deg) > 0.01:
            center = (REF_CANVAS_WIDTH / 2.0, REF_CANVAS_HEIGHT / 2.0)
            rot_mat = cv2.getRotationMatrix2D(center, rotation_deg, 1.0)
            sheet = cv2.warpAffine(
                sheet, rot_mat, (REF_CANVAS_WIDTH, REF_CANVAS_HEIGHT),
                borderMode=cv2.BORDER_REPLICATE
            )

        return sheet

