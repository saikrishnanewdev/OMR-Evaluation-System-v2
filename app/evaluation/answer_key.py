"""Answer-Key Extraction, Validation, and Immutability Management."""
import cv2
import hashlib
import json
import numpy as np
import pymupdf
from pathlib import Path
from typing import Dict, Tuple, List, Optional
from app.models.entities import AnswerKey
from app.config.constants import (
    PDF_RENDER_DPI, TOTAL_QUESTIONS, MODELS_DIR, BUNDLE_DIR
)


class AnswerKeyExtractor:
    """Extracts, verifies, and hashes answer keys from scanned/raster PDF documents."""

    def __init__(self):
        self.templates = self._load_or_build_templates()

    @classmethod
    def _load_or_build_templates(cls) -> Dict[int, np.ndarray]:
        """Loads canonical digit templates from models directory."""
        candidates = [
            MODELS_DIR / "template_digits.npz",
            BUNDLE_DIR / "models" / "template_digits.npz",
            Path("models/template_digits.npz")
        ]
        for p in candidates:
            if p.exists():
                data = np.load(str(p))
                return {
                    1: data["t1"],
                    2: data["t2"],
                    3: data["t3"],
                    4: data["t4"]
                }

        raise FileNotFoundError(
            f"Canonical digit templates 'template_digits.npz' not found in {[str(p) for p in candidates]}. "
            f"Please verify model asset installation."
        )

    def extract_from_pdf(self, pdf_path: Path, exam_id: int = 0) -> AnswerKey:
        """
        Extracts answer key from PDF:
        1. Checks for direct selectable text pairs (e.g. 200Q or 160Q text keys).
        2. Falls back to rendering at 300 DPI, localizing table grid, and template matching.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"Answer key PDF not found: {pdf_path}")

        doc = pymupdf.open(str(pdf_path))
        if len(doc) == 0:
            raise ValueError(f"Empty PDF file: {pdf_path}")

        # Check for direct text-based answer keys (e.g., 200Q or 160Q keys formatted as text)
        text_items = self._extract_from_text(doc)
        if len(text_items) >= 40:
            doc.close()
            key_str = json.dumps({str(k): text_items[k] for k in sorted(text_items.keys())}, sort_keys=True)
            version_hash = hashlib.sha256(key_str.encode("utf-8")).hexdigest()
            return AnswerKey(
                exam_id=exam_id,
                version_number=1,
                version_hash=version_hash,
                is_locked=False,
                source_file=str(pdf_path),
                items=text_items
            )

        # Simple "SL NO / MARKS" list keys (daily/grand tests: T9 20Q,
        # T11 50Q). The numbers run as (question, answer) pairs in
        # reading order — two-column PDFs interleave the columns, so
        # the pairs are still consecutive tokens. Walk the tokens
        # expecting Q=1, answer, Q=2, answer, ... and accept only a
        # complete 1..N run with answers 1-4/A-D, so a stray number
        # or a tabular key can never be misread as a list key.
        list_items = self._extract_from_list_text(doc)
        if list_items:
            doc.close()
            key_str = json.dumps({str(k): list_items[k] for k in sorted(list_items.keys())}, sort_keys=True)
            version_hash = hashlib.sha256(key_str.encode("utf-8")).hexdigest()
            return AnswerKey(
                exam_id=exam_id,
                version_number=1,
                version_hash=version_hash,
                is_locked=False,
                source_file=str(pdf_path),
                items=list_items
            )

        page = doc[0]
        pix = page.get_pixmap(dpi=PDF_RENDER_DPI)
        img_bytes = pix.tobytes("png")
        doc.close()

        nparr = np.frombuffer(img_bytes, np.uint8)
        rendered_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Dynamically detect table grid (rows and answer column positions)
        data_lines, ans_cols = self._detect_grid(rendered_img)

        items = {}
        digit_to_opt = {1: "A", 2: "B", 3: "C", 4: "D"}

        for (x1, x2, start_q) in ans_cols:
            for r_idx in range(len(data_lines) - 1):
                q_num = start_q + r_idx
                y1 = data_lines[r_idx]
                y2 = data_lines[r_idx + 1]
                # Inner crop away from horizontal and vertical grid lines (padding 8px)
                cell = rendered_img[y1 + 8:y2 - 8, x1 + 8:x2 - 8]
                digit, conf = self._classify_cell(cell)
                items[q_num] = digit_to_opt.get(digit, "?")

        # Compute SHA-256 version hash of extracted key
        key_str = json.dumps({str(k): items[k] for k in sorted(items.keys())}, sort_keys=True)
        version_hash = hashlib.sha256(key_str.encode("utf-8")).hexdigest()

        return AnswerKey(
            exam_id=exam_id,
            version_number=1,
            version_hash=version_hash,
            is_locked=False,
            source_file=str(pdf_path),
            items=items
        )

    def _extract_from_text(self, doc: pymupdf.Document) -> Dict[int, str]:
        """Extracts answer key mapping from selectable text inside PDF."""
        import re
        ans_map = {"1": "A", "2": "B", "3": "C", "4": "D", "A": "A", "B": "B", "C": "C", "D": "D"}
        items: Dict[int, str] = {}

        # Strategy 1: Columnar / block-based sequential (question_number, answer_option) pairs
        for page in doc:
            blocks = page.get_text("blocks")
            for b in blocks:
                lines = [l.strip() for l in b[4].split("\n") if l.strip()]
                for i in range(0, len(lines) - 1, 2):
                    if lines[i].isdigit() and lines[i + 1] in ans_map:
                        q = int(lines[i])
                        if 1 <= q <= 300 and q not in items:
                            items[q] = ans_map[lines[i + 1]]

        # Strategy 2: Regex pattern matching across document text if strategy 1 yielded sparse results
        if len(items) < 40:
            items = {}
            full_text = "\n".join(page.get_text() for page in doc)
            matches = re.findall(r"(?:^|\s)(\d{1,3})\s*[\.\:\-\)\t\s]\s*([A-Da-d1-4])(?:\s|$)", full_text)
            for q_str, a_str in matches:
                q = int(q_str)
                if 1 <= q <= 300 and q not in items:
                    items[q] = ans_map.get(a_str.upper(), "?")

        return items

    def _extract_from_list_text(self, doc: pymupdf.Document) -> Dict[int, str]:
        """Parse a plain (question, answer) list key ("SL NO / MARKS").

        The PDF text is a flat run of (question, answer) pairs in
        reading order — a two-column layout interleaves the columns
        (1, 26, 2, 27, ...) but each pair stays consecutive, so pair
        the number tokens in order. A pair is a digit token followed
        by an answer token (1-4 or A-D); any other token is skipped,
        so header text and stray numbers cannot shift the pairs.
        Accept only a complete run Q=1..N (N >= 5), each question
        once, every answer 1-4/A-D. Returns {} when the text is not
        such a list (tabular keys, stray numbers), so the caller
        falls through to grid detection.
        """
        ans_map = {"1": "A", "2": "B", "3": "C", "4": "D",
                   "A": "A", "B": "B", "C": "C", "D": "D"}
        tokens = []
        for page in doc:
            tokens.extend(page.get_text().split())
        items: Dict[int, str] = {}
        i = 0
        while i < len(tokens) - 1:
            q_tok, a_tok = tokens[i], tokens[i + 1]
            if q_tok.isdigit() and a_tok in ans_map:
                q = int(q_tok)
                if 1 <= q <= 300 and q not in items:
                    items[q] = ans_map[a_tok]
                    i += 2
                    continue
            i += 1
        if len(items) >= 5 and set(items) == set(range(1, len(items) + 1)):
            return items
        return {}

    def _detect_grid(self, img: np.ndarray) -> Tuple[List[int], List[Tuple[int, int, int]]]:
        """
        Dynamically detects the 41 row lines and 4 answer column boundaries from the table grid.
        Prevents horizontal/vertical shifts in different PDF scans from including grid border lines.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

        # Horizontal lines in table ROI (x approx 700 to 1700, y approx 150 to 3350)
        table_roi = gray[150:3350, 700:1700]
        _, bin_t = cv2.threshold(table_roi, 180, 255, cv2.THRESH_BINARY_INV)
        h_lines = cv2.morphologyEx(bin_t, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (80, 1)))
        h_sum = np.sum(h_lines, axis=1)

        peaks_y = []
        for y in range(len(h_sum)):
            if h_sum[y] > 0.35 * np.max(h_sum):
                if not peaks_y or y - peaks_y[-1] > 25:
                    peaks_y.append(y)

        data_lines = []
        for i in range(len(peaks_y) - 40):
            diffs = [peaks_y[i + k + 1] - peaks_y[i + k] for k in range(40)]
            if all(55 <= d <= 80 for d in diffs):
                data_lines = [150 + peaks_y[i + k] for k in range(41)]
                break

        # Vertical lines (x lines)
        v_lines = cv2.morphologyEx(bin_t[350:2850], cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 80)))
        v_sum = np.sum(v_lines, axis=0)
        peaks_x = []
        for x in range(len(v_sum)):
            if v_sum[x] > 0.35 * np.max(v_sum):
                if not peaks_x or x - peaks_x[-1] > 20:
                    peaks_x.append(x)

        col_lines = []
        for i in range(len(peaks_x) - 8):
            diffs = [peaks_x[i + k + 1] - peaks_x[i + k] for k in range(8)]
            if all(70 <= d <= 130 for d in diffs):
                col_lines = [700 + peaks_x[i + k] for k in range(9)]
                break

        if len(data_lines) == 41 and len(col_lines) == 9:
            ans_cols = [
                (col_lines[1], col_lines[2], 1),
                (col_lines[3], col_lines[4], 41),
                (col_lines[5], col_lines[6], 81),
                (col_lines[7], col_lines[8], 121),
            ]
            return data_lines, ans_cols

        raise ValueError(
            f"Could not automatically detect answer key table grid lines in PDF (found {len(data_lines)} rows, "
            f"{len(col_lines)} columns). Please ensure the PDF contains a standard 160-question tabular layout."
        )

    def _get_ink_crop(self, cell_bgr: np.ndarray) -> Optional[np.ndarray]:
        gray = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2GRAY)
        ink = gray < 180
        if np.sum(ink) > 0:
            ys, xs = np.where(ink)
            crop = gray[min(ys):max(ys)+1, min(xs):max(xs)+1]
            bin_crop = (crop < 180).astype(np.float32)
            resized = cv2.resize(bin_crop, (20, 28))
            return resized
        return None

    def _classify_cell(self, cell_bgr: np.ndarray) -> Tuple[Optional[int], float]:
        """Classifies a cropped answer cell into 1, 2, 3, or 4 via Normalized Cross-Correlation."""
        crop_bin = self._get_ink_crop(cell_bgr)
        if crop_bin is None:
            return None, 0.0

        best_digit = None
        best_score = -1.0
        for digit, tmpl in self.templates.items():
            if tmpl is None:
                continue
            sc = float(np.sum(crop_bin * tmpl) / (np.sqrt(np.sum(crop_bin**2) * np.sum(tmpl**2)) + 1e-6))
            if sc > best_score:
                best_score = sc
                best_digit = digit

        return best_digit, best_score

    @staticmethod
    def validate_key(items: Dict[int, str], expected_count: int = TOTAL_QUESTIONS) -> List[str]:
        """
        Validates answer key completeness and legality.
        Returns list of error messages (empty if valid).
        """
        errors = []
        valid_opts = {"A", "B", "C", "D"}

        for q in range(1, expected_count + 1):
            if q not in items:
                errors.append(f"Question {q} is missing from the answer key.")
            elif items[q] not in valid_opts:
                errors.append(f"Question {q} has invalid answer '{items[q]}'. Allowed options: A, B, C, D.")

        extra_keys = [q for q in items.keys() if q < 1 or q > expected_count]
        if extra_keys:
            errors.append(f"Answer key contains out-of-range questions: {extra_keys}")

        return errors
