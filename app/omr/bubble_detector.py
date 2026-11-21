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
        timing_marks: Optional[Tuple[List, List]] = None
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
        """
        h, w = ink_map.shape
        results = {}
        thresh_blank = blank_threshold if blank_threshold is not None else self.blank_threshold
        l_marks = timing_marks[0] if (timing_marks and len(timing_marks) == 2) else None
        r_marks = timing_marks[1] if (timing_marks and len(timing_marks) == 2) else None

        for q_num in range(1, self.template.total_questions + 1):
            fills = []
            bg_levels = []

            for opt_idx in range(len(OPTION_NAMES)):
                cx, cy = self.template.get_bubble_center(
                    q_num, opt_idx,
                    timing_marks_left=l_marks,
                    timing_marks_right=r_marks
                )
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

