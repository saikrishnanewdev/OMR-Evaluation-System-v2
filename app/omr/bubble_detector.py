"""Bubble fill analysis, multi-signal feature extraction, and response classification."""
import numpy as np
from typing import Dict, List, Tuple, Optional
from app.omr.template import OMRTemplate, standard_template
from app.config.constants import (
    BUBBLE_RADIUS, BUBBLE_CORE_RADIUS_RATIO,
    FILL_MARKED_THRESHOLD, FILL_BLANK_THRESHOLD,
    FILL_RATIO_MIN, OPTION_NAMES
)


class BubbleDetector:
    """Detects, measures, and classifies candidate responses on OMR bubble grids."""

    def __init__(self, template: OMRTemplate = standard_template, blank_threshold: float = FILL_BLANK_THRESHOLD):
        self.template = template
        self.radius = BUBBLE_RADIUS
        self.core_radius = int(BUBBLE_RADIUS * BUBBLE_CORE_RADIUS_RATIO)
        self.blank_threshold = blank_threshold

        # Precompute circular inner core mask for speed
        size = 2 * self.radius + 1
        y_idx, x_idx = np.ogrid[:size, :size]
        dist = np.sqrt((y_idx - self.radius)**2 + (x_idx - self.radius)**2)
        self.core_mask = dist <= self.core_radius
        self.annular_mask = (dist > self.core_radius) & (dist <= self.radius + 4)

    def analyze_sheet(
        self,
        ink_map: np.ndarray,
        blank_threshold: Optional[float] = None,
        timing_marks: Optional[Tuple[List, List]] = None,
        image_bgr: Optional[np.ndarray] = None
    ) -> Dict[int, Dict]:
        """
        Processes all questions on the ink map.
        Returns a dictionary mapping question_number to:
        {
            'detected_option': str,
            'classification': str, # 'CORRECT'/'WRONG' determined later during scoring; here 'SINGLE', 'BLANK', 'MULTI', 'AMBIGUOUS'
            'confidence': float,
            'fills': [fill_a, fill_b, fill_c, fill_d],
            'max_fill': float,
            'ratio': float
        }

        When image_bgr (the aligned colour sheet) is given, each
        column's row y-centres are corrected to the real detected
        circles (centre sampling, see dynamic
        ._row_centres_from_candidates) instead of the template's
        calibrated grid. The template grid can sit almost a full row
        off when the warp shifts the sheet — on the 200Q Syam sheet
        its rows are ~25 px below the real bubbles at the top of
        each column, so it samples the next row's marks and leaves
        17 near-miss blanks. The x positions stay from the template.
        Without image_bgr the template positions are used as before.
        """
        h, w = ink_map.shape
        results = {}
        thresh_blank = blank_threshold if blank_threshold is not None else self.blank_threshold
        l_marks = timing_marks[0] if (timing_marks and len(timing_marks) == 2) else None
        r_marks = timing_marks[1] if (timing_marks and len(timing_marks) == 2) else None

        # Centre sampling: one true row y per column per row, from
        # the detected circles. None means "use the template y".
        row_ys_by_col = None
        if image_bgr is not None:
            try:
                from app.omr.dynamic import (
                    _candidate_centres, _row_centres_from_candidates)
                img_h, img_w = image_bgr.shape[:2]
                row_ys_by_col = []
                for col_idx in range(self.template.num_columns):
                    base_x = self.template.column_base_x[col_idx]
                    x1 = max(0, int(base_x - 30))
                    x2 = min(img_w, int(base_x + 3 * self.template.option_pitch_x + 30))
                    y1 = max(0, int(self.template.row_base_y - 40))
                    y2 = min(img_h, int(self.template.row_base_y
                                        + (self.template.questions_per_column - 1)
                                        * self.template.row_pitch_y + 40))
                    cands = _candidate_centres(image_bgr, (x1, y1, x2, y2))
                    grid_ys = [self.template.row_base_y
                               + i * self.template.row_pitch_y
                               for i in range(self.template.questions_per_column)]
                    row_ys_by_col.append(
                        _row_centres_from_candidates(
                            cands, self.template.questions_per_column,
                            grid_ys))
            except Exception:
                row_ys_by_col = None

        for q_num in range(1, self.template.total_questions + 1):
            fills = []
            bg_levels = []
            col_idx = (q_num - 1) // self.template.questions_per_column
            row_idx = (q_num - 1) % self.template.questions_per_column

            for opt_idx in range(len(OPTION_NAMES)):
                cx, cy = self.template.get_bubble_center(
                    q_num, opt_idx,
                    timing_marks_left=l_marks,
                    timing_marks_right=r_marks
                )
                if row_ys_by_col is not None:
                    cy = row_ys_by_col[col_idx][row_idx]
                ix, iy = int(round(cx)), int(round(cy))

                # Boundary safety check
                x1 = max(0, ix - self.radius)
                x2 = min(w, ix + self.radius + 1)
                y1 = max(0, iy - self.radius)
                y2 = min(h, iy + self.radius + 1)

                patch = ink_map[y1:y2, x1:x2]
                if patch.shape == (2 * self.radius + 1, 2 * self.radius + 1):
                    core_mean = float(np.mean(patch[self.core_mask]))
                    bg_mean = float(np.mean(patch[self.annular_mask])) if np.sum(self.annular_mask) > 0 else 0.0
                else:
                    core_mean = float(np.mean(patch)) if patch.size > 0 else 0.0
                    bg_mean = 0.0

                fills.append(core_mean)
                bg_levels.append(bg_mean)

            # Sort fills descending to assess best and second-best candidate marks
            sorted_indices = sorted(range(4), key=lambda i: fills[i], reverse=True)
            best_idx = sorted_indices[0]
            second_idx = sorted_indices[1]

            best_fill = fills[best_idx]
            second_fill = fills[second_idx]
            ratio = best_fill / (second_fill + 1e-4)

            # Confidence calculation: combines contrast and dominance ratio
            delta_contrast = max(0.0, best_fill - bg_levels[best_idx])
            dominance = 1.0 - (second_fill / (best_fill + 1e-4))
            raw_conf = (delta_contrast / 160.0) * dominance
            confidence = float(np.clip(raw_conf, 0.0, 1.0))

            # Classification rules:
            if best_fill < thresh_blank:
                detected_opt = "BLANK"
                status = "UNATTEMPTED"
                confidence = float(np.clip(1.0 - (best_fill / max(thresh_blank, 1.0)), 0.5, 1.0))
            elif best_fill >= FILL_MARKED_THRESHOLD and second_fill >= FILL_MARKED_THRESHOLD:
                # Erasure / double mark disambiguation: if dominant mark >= 1.8x second, accept intended answer
                if ratio >= 1.8:
                    detected_opt = OPTION_NAMES[best_idx]
                    status = "SINGLE"
                    confidence = float(np.clip(dominance, 0.4, 0.95))
                else:
                    detected_opt = "MULTI"
                    status = "MULTI"
                    confidence = 0.0
            elif best_fill >= FILL_MARKED_THRESHOLD and ratio >= 1.3:
                detected_opt = OPTION_NAMES[best_idx]
                status = "SINGLE"
            else:
                # Ambiguous / faint mark / erasure
                if ratio >= 1.5 and best_fill >= 45.0:
                    detected_opt = OPTION_NAMES[best_idx]
                    status = "SINGLE"
                else:
                    detected_opt = "AMBIGUOUS"
                    status = "AMBIGUOUS"
                confidence = min(confidence, 0.5)

            results[q_num] = {
                "detected_option": detected_opt,
                "status": status,
                "confidence": round(confidence, 3),
                "fills": [round(f, 2) for f in fills],
                "max_fill": round(best_fill, 2),
                "ratio": round(ratio, 2)
            }

        return results

