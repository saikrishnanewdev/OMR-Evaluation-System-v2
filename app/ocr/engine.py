"""
Offline OCR Engine for Candidate Identification (Hall Ticket and Name).
Performs purely dynamic, local computer vision and neural text recognition.
Incorporates 2.5x bicubic zooming and optical red-color dropout to remove
all pre-printed red/pink box lines, borders, and labels before text extraction.
Zero cloud dependencies, zero hardcoded student tables.
"""
import os
import cv2
import re
import unicodedata
import numpy as np
from pathlib import Path
from typing import Tuple, List, Optional, Dict
from rapidocr_onnxruntime import RapidOCR
try:
    # Optional: only used to point at a local Tesseract binary if one
    # is installed. All real OCR goes through RapidOCR below, so the
    # app must NOT crash at startup when this package is missing —
    # that is what broke the first built .exe (ModuleNotFoundError).
    import pytesseract
except ImportError:  # pragma: no cover - missing optional dependency
    pytesseract = None
from app.omr.preprocessor import Preprocessor
from app.omr.dynamic import find_box_rows, _filled_box_span


def _identity_rows(aligned_bgr: np.ndarray, is_200q: bool):
    """Locate the HT and name box rows on the sheet.

    Returns (ht_row, name_row) BoxRows, or (None, None) when either row
    cannot be found confidently. The fixed reader cuts its HT/name
    strips from hardcoded coordinates, but the warp does not pin the
    rows there (observed HT starts on 200Q sheets: 521, 478, 437), so
    a hardcoded strip cuts off the first boxes (the 388772/388773
    sheets lost the first 2: 'D2025KTS...' for 'KKD2025KTS...',
    'RUTHI' for 'MARUTHI'). Callers use the detected rows to cut
    their strips instead.
    """
    if is_200q:
        ht_band, name_band = (175, 226), (225, 275)
    else:
        ht_band, name_band = (208, 266), (254, 314)
    try:
        rows = find_box_rows(aligned_bgr)
    except Exception:
        return None, None

    def _pick(band):
        cands = [r for r in rows
                 if band[0] <= r.y <= band[1] and r.num_boxes >= 10]
        if not cands:
            return None
        centre = (band[0] + band[1]) // 2
        return max(cands, key=lambda r: (r.num_boxes, -abs(r.y - centre)))

    return _pick(ht_band), _pick(name_band)

# Configure local offline Tesseract binary path if available
if pytesseract is not None:
    TESSERACT_CANDIDATE_PATHS = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")
    ]
    for p in TESSERACT_CANDIDATE_PATHS:
        if os.path.exists(p):
            pytesseract.pytesseract.tesseract_cmd = p
            break


class OCREngine:
    """
    Performs purely dynamic offline recognition of handwritten identification fields.
    Does NOT hardcode student names or roll numbers.
    """

    HT_PATTERN = re.compile(r"^[A-Z0-9]{4,20}$")
    REF_TL_X = 106.0
    REF_TL_Y = 189.0

    # Character-to-digit confusion matrix for handwritten digits in printed boxes
    CHAR_TO_DIGIT = {
        '0': '0', '1': '1', '2': '2', '3': '3', '4': '4',
        '5': '5', '6': '6', '7': '7', '8': '8', '9': '9',
        'O': '0', 'D': '0', 'C': '0', 'Q': '0', 'U': '0',
        'o': '0', 'd': '0', 'c': '0', 'u': '0',
        'I': '1', 'L': '1', 'J': '1', '|': '1', '/': '1', '\\': '1', '!': '1', 'i': '1', 'l': '1',
        'j': '1', '(': '1', ')': '1', '[': '1', ']': '1', '{': '1', '}': '1', '-': '1', '_': '1',
        'Z': '2', 'z': '2', '&': '2',
        'E': '3',
        'A': '4', 'Y': '4', 'H': '4',
        'S': '5', 's': '5',
        'G': '6', 'b': '6',
        'T': '7', 'F': '7', 'f': '7', '+': '7', '=': '7', 't': '7',
        'B': '8',
        'q': '9', 'g': '9',
    }

    def __init__(self):
        self.ocr = RapidOCR()

    @staticmethod
    def remove_red_color(img_bgr: np.ndarray) -> np.ndarray:
        """
        Precisely removes pre-printed red/pink/brown form lines, boxes, and text.
        Leaves dark student handwriting on pure white background.
        """
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        
        # Red hue wrap-around in HSV: 0-20 and 160-180 with moderate saturation and brightness
        is_red_hsv = ((h < 20) | (h > 160)) & (s > 25) & (v > 80)
        
        # Also check RGB: red component substantially higher than green and blue
        b, g, r = cv2.split(img_bgr)
        is_red_rgb = (r > 115) & (r.astype(int) - g.astype(int) > 15) & (r.astype(int) - b.astype(int) > 15)
        
        red_mask = is_red_hsv | is_red_rgb
        cleaned = img_bgr.copy()
        cleaned[red_mask] = [255, 255, 255]
        return cleaned

    def _extract_candidate_name(self, name_raw: np.ndarray, is_200q: bool = False) -> Tuple[str, float, np.ndarray]:
        """
        Extracts candidate name across candidate name boxes.
        Only called when Hall Ticket is missing or unreadable, or for dual-signal validation.
        """
        z_nm = cv2.resize(name_raw, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        clean_nm = self.remove_red_color(z_nm)
        gray_nm = cv2.cvtColor(clean_nm, cv2.COLOR_BGR2GRAY)

        if is_200q:
            num_boxes = 24
            box_pitch_z = clean_nm.shape[1] / 24.0
            x_start_z = 0.0
        else:
            num_boxes = 20
            box_pitch_z = 98.375
            x_start_z = 22.5

        # Initial box punctuation dot cleanup (e.g. 'P.', 'K.', 'S.' where pen dot at bottom foot turns P into R)
        has_initial_dot = False
        bx1_0 = int(round(x_start_z))
        bx2_0 = int(round(x_start_z + box_pitch_z))
        if bx2_0 <= clean_nm.shape[1]:
            box1_patch = clean_nm[:, bx1_0:bx2_0]
            gray_b1 = cv2.cvtColor(box1_patch, cv2.COLOR_BGR2GRAY)
            _, thresh_b1 = cv2.threshold(gray_b1, 180, 255, cv2.THRESH_BINARY_INV)
            n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(thresh_b1)
            for i in range(1, n_labels):
                x_c, y_c, w_c, h_c, a_c = stats[i]
                if a_c < 80 and y_c > 50 and w_c <= 20 and h_c <= 20:
                    has_initial_dot = True
                    box1_patch[labels == i] = [255, 255, 255]

        # Box-level ink density scan across all boxes (Pillar 3: Physical Box-Grid ICR)
        box_inks = []
        for b in range(num_boxes):
            bx1 = int(round(x_start_z + b * box_pitch_z))
            bx2 = int(round(x_start_z + (b + 1) * box_pitch_z))
            patch = gray_nm[12:-12, max(0, bx1 + 8):min(gray_nm.shape[1], bx2 - 8)]
            ink = int(np.sum(patch < 180))
            box_inks.append(ink)

        # Detect active box range
        first_b = 0
        while first_b < num_boxes and box_inks[first_b] < 200:
            first_b += 1
        last_b = num_boxes
        while last_b > first_b and box_inks[last_b - 1] < 200:
            last_b -= 1

        if first_b >= last_b:
            return "", 0.0, clean_nm

        # Check for isolated initial box (e.g. Box 0 or 1 filled, followed by empty box)
        initial_char = ""
        start_body_b = first_b
        if (first_b <= 1) and (first_b + 1 < last_b) and (box_inks[first_b + 1] < 200):
            bx1 = int(round(x_start_z + first_b * box_pitch_z))
            bx2 = int(round(x_start_z + (first_b + 1) * box_pitch_z))
            init_crop = clean_nm[:, max(0, bx1 - 5):min(clean_nm.shape[1], bx2 + 5)]
            pad_i = cv2.copyMakeBorder(init_crop, 15, 15, 25, 25, cv2.BORDER_CONSTANT, value=[255, 255, 255])
            h_i, w_i = pad_i.shape[:2]
            scaled_i = cv2.resize(pad_i, (int(w_i * 48.0 / h_i), 48), interpolation=cv2.INTER_AREA)
            preds_i, _ = self.ocr.text_recognizer([scaled_i])
            if preds_i and preds_i[0][0]:
                raw_c = preds_i[0][0].strip()
                digit_to_letter = {'6': 'G', '0': 'O', '1': 'I', '8': 'B', '5': 'S', '2': 'Z'}
                if raw_c in digit_to_letter:
                    initial_char = digit_to_letter[raw_c]
                else:
                    clean_i = re.sub(r'[^A-Za-z]', '', raw_c).upper()
                    if clean_i:
                        initial_char = clean_i[0]

            start_body_b = first_b + 2
            while start_body_b < last_b and box_inks[start_body_b] < 200:
                start_body_b += 1

        # Extract body or full name strip
        if initial_char and start_body_b < last_b:
            body_x1 = int(round(x_start_z + start_body_b * box_pitch_z)) - 10
            body_x2 = int(round(x_start_z + last_b * box_pitch_z)) + 10
            body_crop = clean_nm[:, max(0, body_x1):min(clean_nm.shape[1], body_x2)].copy()
        else:
            body_x1 = int(round(x_start_z + first_b * box_pitch_z)) - 10
            body_x2 = int(round(x_start_z + last_b * box_pitch_z)) + 10
            body_crop = clean_nm[:, max(0, body_x1):min(clean_nm.shape[1], body_x2)].copy()

        pad_nm = cv2.copyMakeBorder(body_crop, 15, 15, 30, 30, cv2.BORDER_CONSTANT, value=[255, 255, 255])

        h_n, w_n = pad_nm.shape[:2]
        scaled_n = cv2.resize(pad_nm, (int(w_n * 48.0 / h_n), 48), interpolation=cv2.INTER_AREA)
        preds_nm, _ = self.ocr.text_recognizer([scaled_n])
        raw_nm = preds_nm[0][0] if preds_nm else ""

        norm_nm = unicodedata.normalize('NFKC', raw_nm)
        clean_nm_str = re.sub(r"[^A-Za-z\s]", " ", norm_nm)
        # Remove trailing ghost characters from empty box vertical lines (e.g. LLLLLI, ILLLLI, LLLLE)
        clean_nm_str = re.sub(r'([A-Za-z]{3,})\s*[IL1\|!EFC]{2,}\s*$', r'\1', clean_nm_str)
        clean_nm_str = re.sub(r"[IL1\|!EFC]+$", "", clean_nm_str)
        clean_nm_str = re.sub(r"[\s\|\!]+$", "", clean_nm_str)
        clean_nm_str = re.sub(r"^[\s\|\!]+", "", clean_nm_str)
        clean_nm_str = re.sub(r"\s+[\|\!]+\s*", " ", clean_nm_str)

        body_text = " ".join(clean_nm_str.split()).upper()
        if initial_char:
            name_final = f"{initial_char} {body_text}".strip()
        else:
            name_final = body_text

        if len(name_final) < 3:
            name_final = ""

        name_conf = float(preds_nm[0][1]) if (name_final and preds_nm and preds_nm[0][1] > 0.05) else 0.0
        return name_final, name_conf, pad_nm

    def extract_identity(
        self,
        aligned_bgr: np.ndarray,
        exam_prefix: Optional[str] = None,
        roster: Optional[List[Dict[str, str]]] = None,
        return_crops: bool = False,
        is_200q: Optional[bool] = None
    ):
        """
        Dynamically extracts Hall Ticket Number and Candidate Name from an aligned sheet image.
        Supports both standard 160Q DSC layout and 200Q AP SI Mains layout.
        Uses 2.5x bicubic zooming followed by red color removal to erase grid lines before OCR.
        
        Args:
            aligned_bgr: Sheet image aligned to reference canvas (1644, 2272).
            exam_prefix: Optional exam identifier prefix configured for the examination.
                         If None, extraction dynamically recognizes the characters directly from the sheet.
            roster: Optional imported student registry list [{'roll': ..., 'name': ...}].
                   If None, extraction is 100% dynamic without roster matching.
            return_crops: If True, returns a 5-tuple (ht, name, conf, is_valid, crops_dict).
            is_200q: Optional boolean indicating 200Q geometry. If None, auto-detected from timing tracks.
                   
        Returns:
            Tuple of (hall_ticket_str, candidate_name_str, confidence_score, is_valid_pattern)
            or 5-tuple with crops_dict if return_crops=True.
        """
        # Auto-detect 200Q layout if not explicitly provided
        if is_200q is None:
            left_marks, right_marks, _ = Preprocessor.detect_timing_tracks(aligned_bgr)
            is_200q = (len(left_marks) >= 53 or len(right_marks) >= 53)

        # 0. Follow the printed rows. The fixed strips below assume the
        # HT/name rows start at x=515 (200Q) / x=440 (160Q), but the warp
        # does not pin the rows there (observed starts 437-521), so a
        # hardcoded strip cuts off the first boxes. When both rows are
        # found on the sheet, cut the strips from the rows themselves,
        # trimmed to the filled boxes (as the dynamic reader does) so
        # the OCR does not invent letters from the empty boxes. When a
        # row cannot be found, or a field is blank, fall back to the
        # hardcoded coordinates (behaviour exactly as before).
        ht_row, name_row = _identity_rows(aligned_bgr, is_200q)
        row_based = ht_row is not None and name_row is not None
        if row_based:
            # If the row is already where the template expects it
            # (within half a box), keep the hardcoded strip: its
            # geometry is the known-good one the OCR was tuned on
            # (348819 reads '00627' there — 1 digit off and
            # roster-fixable — while a row-based strip reads '50162'
            # on the same handwriting). Only follow the row when it
            # is actually shifted.
            template_x1 = 515 if is_200q else 440
            if abs(ht_row.x1 - template_x1) <= 15:
                row_based = False
        if row_based:
            ht_span = _filled_box_span(aligned_bgr, ht_row)
            name_span = _filled_box_span(aligned_bgr, name_row)
            if ht_span is None or name_span is None:
                row_based = False
        if row_based:
            # A small margin around the row: the detected row bounds are
            # the printed outlines, and a strip cut exactly to them
            # clips character tops/bottoms and reads worse (348819's
            # '7' read as '4' in a tight strip, '7' in a margined one).
            # Both strips are trimmed to the filled boxes so the OCR
            # does not invent letters from the empty boxes — a full-row
            # strip spaces the characters out and trips the missing-HT
            # check on short hall tickets (img0076's AP05CJ1798).
            m = 6
            h_img, w_img = aligned_bgr.shape[:2]
            ht_x1 = max(0, ht_row.boxes[ht_span[0]][0] - m)
            ht_x2 = min(w_img, ht_row.boxes[ht_span[1]][0]
                        + ht_row.boxes[ht_span[1]][2] + m)
            ht_raw = aligned_bgr[max(0, ht_row.y1 - m):ht_row.y2 + m,
                                 ht_x1:ht_x2]
            nm_x1 = max(0, name_row.boxes[name_span[0]][0] - m)
            nm_x2 = min(w_img, name_row.boxes[name_span[1]][0]
                        + name_row.boxes[name_span[1]][2] + m)
            name_raw = aligned_bgr[max(0, name_row.y1 - m):name_row.y2 + m,
                                   nm_x1:nm_x2]
            # Roll digits are boxes 11-15 of the HT row (200Q: 10-char
            # prefix + 5-digit roll; 160Q: 11-char prefix + 5-digit
            # roll). The ink check covers them.
            ht_box_w = (ht_row.x2 - ht_row.x1) / float(ht_row.num_boxes)
            roll_first = 10 if is_200q else 11
            roll_x1 = int(round(ht_row.x1 + roll_first * ht_box_w))
            roll_area = aligned_bgr[ht_row.y1:ht_row.y2,
                                    roll_x1:ht_row.x2]
        else:
            # 1. Coordinate regions on calibrated canvas (1644 x 2272)
            if is_200q:
                ht_raw = aligned_bgr[175:226, 515:1115]
                name_raw = aligned_bgr[225:275, 515:1485]
                roll_area = aligned_bgr[175:226, 880:1115]
            else:
                ht_raw = aligned_bgr[208:266, 440:1145]
                name_raw = aligned_bgr[254:314, 442:1248]
                roll_area = aligned_bgr[220:259, 840:1060]
            ht_box_w = None
            roll_first = 10 if is_200q else 11
        
        # Check ink in the 5 roll number boxes (in inverted Red channel)
        _, _, r_roll = cv2.split(roll_area)
        roll_ink = int(np.sum(r_roll < 160))
        _, _, r_ht = cv2.split(ht_raw)
        ht_ink = int(np.sum(r_ht < 160))

        # Check cleaned ink to verify if handwriting exists (erasing printed box borders)
        z_ht = cv2.resize(ht_raw, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        cl_ht = self.remove_red_color(z_ht)
        gray_cl_ht = cv2.cvtColor(cl_ht, cv2.COLOR_BGR2GRAY)
        cleaned_ht_ink = int(np.sum(gray_cl_ht < 160))

        # CASE 1: Physical Blank in Hall Ticket (< 80 ink pixels in roll boxes and < 250 in full HT, or cleaned ink < 500)
        # Hall Ticket is definitely missing -> check candidate name as fallback
        if (roll_ink < 80 and ht_ink < 250) or cleaned_ht_ink < 500:
            name_final, name_conf, pad_nm = self._extract_candidate_name(name_raw, is_200q=is_200q)
            final_ht = ""
            if roster:
                r_ht, r_name = self._reconcile_with_roster("", name_final, "", roster, preferred_prefix=exam_prefix)
                if r_name:
                    name_final = r_name
                if r_ht:
                    final_ht = r_ht
            if return_crops:
                pad_ht = cv2.copyMakeBorder(cl_ht, 15, 15, 30, 30, cv2.BORDER_CONSTANT, value=[255, 255, 255])
                crops = {
                    "ht_processed": pad_ht,
                    "name_processed": pad_nm,
                    "ht_raw": ht_raw,
                    "name_raw": name_raw,
                    "ht_missing_on_sheet": True
                }
                return final_ht, name_final, name_conf, bool(final_ht), crops
            return final_ht, name_final, name_conf, bool(final_ht)
            
        # 2. ZOOM IN & OPTICAL RED COLOR DROPOUT on Hall Ticket Strip + Margin Padding
        pad_ht = cv2.copyMakeBorder(cl_ht, 15, 15, 30, 30, cv2.BORDER_CONSTANT, value=[255, 255, 255])
            
        # 3. Dynamic Hall Ticket Recognition on Full Strip
        h_h, w_h = pad_ht.shape[:2]
        scaled_h = cv2.resize(pad_ht, (int(w_h * 48.0 / h_h), 48), interpolation=cv2.INTER_AREA)
        preds_ht, _ = self.ocr.text_recognizer([scaled_h])
        raw_ht = preds_ht[0][0] if preds_ht else ""

        # CASE 2: Left-aligned ink check: if roll_ink < 80 and raw_ht lacks candidate sequence, HT is missing
        if roll_ink < 80 and not re.search(r'[A-Za-z]{2,}\d{4,5}', raw_ht):
            name_final, name_conf, pad_nm = self._extract_candidate_name(name_raw, is_200q=is_200q)
            final_ht = ""
            if roster:
                r_ht, r_name = self._reconcile_with_roster("", name_final, "", roster, preferred_prefix=exam_prefix)
                if r_name:
                    name_final = r_name
                if r_ht:
                    final_ht = r_ht
            if return_crops:
                crops = {
                    "ht_processed": pad_ht,
                    "name_processed": pad_nm,
                    "ht_raw": ht_raw,
                    "name_raw": name_raw,
                    "ht_missing_on_sheet": True
                }
                return final_ht, name_final, name_conf, bool(final_ht), crops
            return final_ht, name_final, name_conf, bool(final_ht)

        # 4. Secondary Roll Strip Recognition (focused roll boxes)
        # Avoids prefix bleed and phantom borders, ensuring clean recognition of digits.
        if row_based:
            # Roll digits sit at boxes roll_first..roll_first+4 of the
            # detected row; convert the strip-relative position to pad_ht
            # coordinates (2.5x zoom + 30px left padding).
            roll_start_x = int(round(
                2.5 * ((ht_row.x1 + roll_first * ht_box_w) - ht_x1) + 30))
            roll_end_default = min(
                pad_ht.shape[1],
                int(round(2.5 * ((ht_row.x1 + (roll_first + 5) * ht_box_w)
                                 - ht_x1) + 30)))
        elif is_200q:
            roll_start_x = 912
            roll_end_default = min(pad_ht.shape[1], 1354)
        else:
            roll_start_x = 1147
            roll_end_default = min(pad_ht.shape[1], 1147 + 518)

        roll_part = pad_ht[:, roll_start_x:]
        gray_r = cv2.cvtColor(roll_part, cv2.COLOR_BGR2GRAY)
        if not is_200q:
            outside_band = gray_r[35:140, 518:]
            y_ink, x_ink = np.where(outside_band < 180)
            if len(x_ink) > 0 and np.sum(outside_band < 180) > 150:
                # Candidate wrote extra numbers outside the boxes: dynamically extend crop to capture them
                end_x = min(pad_ht.shape[1], roll_start_x + 518 + int(np.max(x_ink)) + 30)
            else:
                end_x = roll_end_default
        else:
            # 200Q Layout has 17 boxes total (10 prefix + 5 roll + 2 trailing empty). Ignore trailing empty boxes.
            end_x = roll_end_default
            
        roll_crop = pad_ht[:, roll_start_x:end_x]
        h_r, w_r = roll_crop.shape[:2]
        scaled_r = cv2.resize(roll_crop, (int(w_r * 48.0 / h_r), 48), interpolation=cv2.INTER_AREA)
        preds_r, _ = self.ocr.text_recognizer([scaled_r])
        raw_roll = preds_r[0][0] if preds_r else ""
        
        # 8. Dynamic Roll Digit Assembly via Multi-Signal Mapping with Unicode NFKC Normalization
        norm_ht = unicodedata.normalize('NFKC', raw_ht)
        # Pre-map crossed-7 symbols (+, =) into '7' before stripping non-alphanumeric chars
        norm_ht = norm_ht.replace('+', '7').replace('=', '7')
        clean_ht = re.sub(r'[^A-Za-z0-9]', '', norm_ht).upper()
        norm_roll = unicodedata.normalize('NFKC', raw_roll).replace('+', '7').replace('=', '7')

        # Check if clean_ht contains digits followed by trailing stray noise characters
        m_noise = re.search(r'^(.*?)(\d{1,5})([A-Z]{1,2})$', clean_ht)
        if m_noise and not any(c in ('S', 'O', 'I', 'Z') for c in m_noise.group(3)):
            clean_ht = m_noise.group(1) + m_noise.group(2)

        # Disambiguate any trailing letters that follow digits at the end of the hall ticket string
        disambiguated_chars = list(clean_ht)
        for i in range(len(disambiguated_chars) - 1, -1, -1):
            c = disambiguated_chars[i]
            if c.isdigit():
                break
            elif c in self.CHAR_TO_DIGIT:
                disambiguated_chars[i] = self.CHAR_TO_DIGIT[c]
            else:
                break
        disambiguated_ht = "".join(disambiguated_chars)

        mapped_roll_chars = [self.CHAR_TO_DIGIT.get(c, '') for c in norm_roll if c in self.CHAR_TO_DIGIT or c.isalnum()]
        mapped_roll_str = "".join(mapped_roll_chars)

        m_strip = re.search(r'\d{1,5}$', disambiguated_ht)
        strip_digits = m_strip.group(0) if m_strip else ""

        c_roll = float(preds_r[0][1]) if preds_r and preds_r[0][1] > 0.05 else 0.0
        c_ht = float(preds_ht[0][1]) if preds_ht and preds_ht[0][1] > 0.05 else 0.0

        # Expected roll length: the trailing digits after the exam prefix.
        # The merge below hardcodes a 5-digit roll (KTS/160Q formats),
        # but the AP format has a 4-digit roll (AP05CJ1798) — padding it
        # to 5 invents a leading 0 ('AP05CJ01798'). When the rows were
        # found, the filled boxes give the true hall-ticket length, so
        # the roll length is exact even when the OCR drops a leading
        # zero ('0211' -> '00211'). Otherwise (no rows found) keep the
        # long-standing 5.
        if row_based:
            num_filled = ht_span[1] - ht_span[0] + 1
            if exam_prefix and exam_prefix.strip():
                # The exam prefix may belong to a different exam than
                # the sheet (roster prefix KKD on an AP sheet): if it
                # is longer than the sheet's hall ticket it cannot be
                # this sheet's prefix, so use the sheet's own prefix
                # length instead.
                exp_from_exam = num_filled - len(exam_prefix.strip())
                if 1 <= exp_from_exam <= 6:
                    expected_roll_len = exp_from_exam
                else:
                    p_len = (len(disambiguated_ht) - len(strip_digits)
                             if strip_digits else len(disambiguated_ht))
                    expected_roll_len = num_filled - p_len
            elif strip_digits:
                expected_roll_len = num_filled - (
                    len(disambiguated_ht) - len(strip_digits))
            else:
                expected_roll_len = 5
        else:
            expected_roll_len = 5
        if expected_roll_len < 1 or expected_roll_len > 6:
            expected_roll_len = 5

        roll_source = "roll"
        roll_num_str = ""

        # Reconcile roll digits between secondary roll strip and full strip
        if len(strip_digits) == expected_roll_len and strip_digits.isdigit() and (len(mapped_roll_str) != expected_roll_len or c_ht >= c_roll):
            roll_num_str = strip_digits
            roll_source = "strip"
        elif len(mapped_roll_str) == expected_roll_len and mapped_roll_str.isdigit():
            roll_num_str = mapped_roll_str
            roll_source = "roll"
        elif len(strip_digits) >= 3 and strip_digits.isdigit() and c_ht >= c_roll - 0.05:
            roll_num_str = strip_digits.zfill(expected_roll_len)
            roll_source = "strip"
        elif len(mapped_roll_str) >= 1 and mapped_roll_str.isdigit():
            roll_num_str = mapped_roll_str[-expected_roll_len:].zfill(expected_roll_len)
            roll_source = "roll"
        elif len(strip_digits) >= 1:
            roll_num_str = strip_digits.zfill(expected_roll_len)
            roll_source = "strip"

        # 4b. Sliced per-box digit classification for ambiguous or short roll numbers
        if len(roll_num_str) < expected_roll_len or roll_num_str == "0" * expected_roll_len:
            box_digits = []
            if row_based:
                # Boxes of the detected row, in cl_ht coordinates (2.5x
                # the strip); x_start_ht is the row start within the
                # strip (0 when the filled span starts at box 1).
                box_w_ht = 2.5 * ht_box_w
                x_start_ht = 2.5 * (ht_row.x1 - ht_x1)
                range_boxes = range(roll_first, roll_first + 5)
            elif is_200q:
                box_w_ht = 1500.0 / 17.0  # 17 boxes total (10 prefix + 5 roll + 2 trailing empty)
                x_start_ht = 0.0
                range_boxes = range(10, 15)
            else:
                box_w_ht = 98.375
                x_start_ht = 22.5
                range_boxes = range(11, 16)

            for b in range_boxes:
                bx1 = int(round(x_start_ht + b * box_w_ht + 5))
                bx2 = int(round(x_start_ht + (b + 1) * box_w_ht - 5))
                if bx2 <= cl_ht.shape[1]:
                    box_crop = cl_ht[:, bx1:bx2]
                    d, _ = self.classify_digit_box(box_crop)
                    if d:
                        box_digits.append(d)
            if len(box_digits) >= 1:
                box_roll_str = "".join(box_digits).zfill(expected_roll_len)
                if not roll_num_str or len(mapped_roll_str) < len(box_digits):
                    roll_num_str = box_roll_str
                    roll_source = "box_classifier"

        if exam_prefix and exam_prefix.strip():
            # If candidate clearly wrote a different distinct prefix (e.g. CDVM vs KNL),
            # preserve the sheet's own prefix; otherwise use exam_prefix to correct OCR noise
            if strip_digits and len(disambiguated_ht) > len(strip_digits) + 3:
                p_sheet = disambiguated_ht[:-len(strip_digits)]
                if is_200q:
                    p_sheet = re.sub(r'R[5S]Y', 'RJY', p_sheet, flags=re.IGNORECASE)
                    p_sheet = re.sub(r'KK[0-9]', 'KKD2', p_sheet, flags=re.IGNORECASE)
                    p_sheet = re.sub(r'^([A-Z])5([A-Z])', r'\g<1>S\g<2>', p_sheet)
                    p_sheet = re.sub(r'K[7TF\+\=][358SsZz]', 'KTS', p_sheet, flags=re.IGNORECASE)

                p_exam = exam_prefix.strip()
                from difflib import SequenceMatcher
                # Compare the whole prefixes, not just the leading
                # letters: a 2-letter district code ('AP' in AP05CJ)
                # is a genuine different exam from KKD, while a short
                # OCR fragment ('KD' of KKD) must not override the
                # exam prefix. A sheet prefix of >= 4 chars that is
                # very dissimilar to the exam prefix is kept as-is.
                sim_prefix = SequenceMatcher(None, p_sheet, p_exam).ratio()
                is_different_district = (
                    len(p_sheet) >= 4 and sim_prefix < 0.40
                )

                if is_different_district:
                    final_ht = f"{p_sheet}{roll_num_str}"
                else:
                    final_ht = f"{p_exam}{roll_num_str}"
            else:
                final_ht = f"{exam_prefix.strip()}{roll_num_str}"
        else:
            if strip_digits:
                prefix_part = disambiguated_ht[:-len(strip_digits)]
                if is_200q:
                    prefix_part = re.sub(r'R[5S]Y', 'RJY', prefix_part, flags=re.IGNORECASE)
                    prefix_part = re.sub(r'KK[0-9]', 'KKD2', prefix_part, flags=re.IGNORECASE)
                    prefix_part = re.sub(r'^([A-Z])5([A-Z])', r'\g<1>S\g<2>', prefix_part)
                    prefix_part = re.sub(r'K[7TF\+\=][358SsZz]', 'KTS', prefix_part, flags=re.IGNORECASE)
                final_ht = f"{prefix_part}{roll_num_str}"
            else:
                final_ht = disambiguated_ht

        # CASE 3: If Hall Ticket is missing (empty, all zeros, or lacks sequence)
        if not final_ht or roll_num_str == "00000" or not re.search(r'\d{3,5}$', final_ht):
            # Check candidate name ONLY because hallticket number is missing
            name_final, name_conf, pad_nm = self._extract_candidate_name(name_raw, is_200q=is_200q)
            resolved_ht = ""
            if roster:
                r_ht, r_name = self._reconcile_with_roster("", name_final, "", roster, preferred_prefix=exam_prefix)
                if r_name:
                    name_final = r_name
                if r_ht:
                    resolved_ht = r_ht
            if return_crops:
                crops = {
                    "ht_processed": pad_ht,
                    "name_processed": pad_nm,
                    "ht_raw": ht_raw,
                    "name_raw": name_raw,
                    "ht_missing_on_sheet": True
                }
                return resolved_ht, name_final, name_conf, bool(resolved_ht), crops
            return resolved_ht, name_final, name_conf, bool(resolved_ht)

        # CASE 4: Hall Ticket is present and valid!
        # Always extract candidate name to enable dual-signal validation and complete records
        name_final, name_conf, pad_nm = self._extract_candidate_name(name_raw, is_200q=is_200q)
        is_valid = bool(self.HT_PATTERN.match(final_ht))
        
        # 8. Optional Roster Reconciliation (Dual-Signal: HT + Name Co-Verification)
        if roster:
            resolved_ht, resolved_name = self._reconcile_with_roster(
                final_ht, name_final, raw_ht, roster, secondary_roll=mapped_roll_str, preferred_prefix=exam_prefix
            )
            if resolved_ht:
                final_ht = resolved_ht
                is_valid = True
            if resolved_name:
                name_final = resolved_name

        # 9. Dynamic OCR Recognition Confidence Assessment
        c_roll = float(preds_r[0][1]) if preds_r and preds_r[0][1] > 0.05 else 0.0
        c_ht = float(preds_ht[0][1]) if preds_ht and preds_ht[0][1] > 0.05 else 0.0

        if roll_source == "roll" and c_roll > 0:
            conf = max(c_roll, c_ht)
        elif c_ht > 0:
            conf = c_ht
        elif c_roll > 0:
            conf = c_roll
        else:
            conf = 0.50

        if return_crops:
            crops = {
                "ht_processed": pad_ht,
                "name_processed": pad_nm,
                "ht_raw": ht_raw,
                "name_raw": name_raw,
                "ht_missing_on_sheet": False
            }
            return final_ht, name_final, conf, is_valid, crops

        return final_ht, name_final, conf, is_valid

    def classify_digit_box(self, box_bgr: np.ndarray) -> Tuple[str, float]:
        """
        Classifies an isolated character box strictly into digits 0-9 using logit constraints.
        Resolves cursive 2s, crossed 7s, and ambiguous 5s with 100% digit purity.
        """
        gray = cv2.cvtColor(box_bgr, cv2.COLOR_BGR2GRAY) if len(box_bgr.shape) == 3 else box_bgr
        if np.sum(gray < 180) < 60:
            return "", 0.0
        h, w = box_bgr.shape[:2]
        wh_ratio = w * 1.0 / h
        rec = self.ocr.text_recognizer
        norm_img = rec.resize_norm_img(box_bgr, wh_ratio)[np.newaxis, :].astype(np.float32)
        preds = rec.session(norm_img)[0]
        
        char_list = rec.character_dict_path
        digit_scores = {d: float(np.max(preds[0, :, char_list.index(d) + 1])) for d in '0123456789' if d in char_list}
        if not digit_scores:
            return "", 0.0
        sorted_d = sorted(digit_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_d[0][0], sorted_d[0][1]

    def _reconcile_with_roster(
        self,
        candidate_ht: str,
        candidate_name: str,
        raw_ht: str,
        roster: List[Dict[str, str]],
        secondary_roll: Optional[str] = None,
        preferred_prefix: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Dual-signal fuzzy matching against an imported examination roster.
        Co-verifies Hall Ticket (including full prefix & roll digits) and Candidate Name.
        Resolves collisions when multiple students share identical roll suffixes.
        Supports windowed root-name matching and initial expansion for Indian names.
        """
        from difflib import SequenceMatcher
        best_match = None
        best_score = 0.0

        cand_name_upper = candidate_name.upper().strip()
        cand_ht_upper = candidate_ht.upper().strip()
        clean_raw_ht = re.sub(r'[^A-Z0-9]', '', raw_ht.upper())
        sec_roll_u = secondary_roll.upper().strip() if secondary_roll else ""

        clean_name = re.sub(r'^[I\|\!\s]+', '', cand_name_upper).strip()
        c_parts = clean_name.split()
        name_nospace = re.sub(r'\s+', '', clean_name)

        # A hall ticket always has digits. A candidate with no digit
        # at all (a garbled read like 'TAL' from the 50Q grand-test
        # sheet) counts as absent: it must not poison a good name
        # match through the dual-signal combination below. With no
        # usable HT the name-only path runs instead.
        has_cand_ht = bool(cand_ht_upper and cand_ht_upper != "00000"
                           and any(c.isdigit() for c in cand_ht_upper))
        has_cand_name = bool(len(clean_name) >= 3)

        # Extract district prefix for scoped search partitioning (Pillar 2)
        pref_dist = ""
        if preferred_prefix:
            m_dist = re.match(r'^[A-Z]+', preferred_prefix.strip())
            if m_dist:
                pref_dist = m_dist.group(0)

        for record in roster:
            r_roll = record.get("roll", "").upper().strip()
            r_name = record.get("name", "").upper().strip()
            r_parts = r_name.split()
            rn_nospace = re.sub(r'\s+', '', r_name)

            # A roster row with a roll number but no name must not win
            # on a fuzzy hall-ticket match: a garbled read can be
            # "near" a nameless row and steal the record (348819:
            # 'KKD2025K7300694' matched 'KKD2025KTS00645', blank name).
            # A nameless row may only match on an exact hall ticket.
            if not r_name and has_cand_name:
                exact_ht = bool(
                    r_roll and has_cand_ht
                    and (cand_ht_upper == r_roll
                         or (clean_raw_ht and clean_raw_ht == r_roll)))
                if not exact_ht:
                    continue

            # --- Dimension 1: Hall Ticket Matching Score (0.0 to 1.0) ---
            ht_score = 0.0
            if r_roll and has_cand_ht:
                if cand_ht_upper == r_roll or (clean_raw_ht and clean_raw_ht == r_roll):
                    ht_score = 1.0
                else:
                    s1 = SequenceMatcher(None, cand_ht_upper, r_roll).ratio()
                    s2 = SequenceMatcher(None, clean_raw_ht, r_roll).ratio() if clean_raw_ht else 0.0
                    full_sim = max(s1, s2)

                    # Extract roll numbers (last 3-5 digits)
                    d_cand = re.findall(r'\d+', cand_ht_upper or clean_raw_ht)
                    d_roster = re.findall(r'\d+', r_roll)
                    d_sec = re.findall(r'\d+', sec_roll_u) if sec_roll_u else []

                    digits_match = False
                    d_near_match = False
                    d_sim = 0.0
                    if d_roster:
                        r_digs = d_roster[-1][-5:].zfill(5)
                        c_digs = d_cand[-1][-5:].zfill(5) if d_cand else ""
                        s_digs = d_sec[-1][-5:].zfill(5) if d_sec else ""
                        if (c_digs and c_digs == r_digs) or (s_digs and s_digs == r_digs):
                            digits_match = True
                        else:
                            sim_c = SequenceMatcher(None, c_digs, r_digs).ratio() if c_digs else 0.0
                            sim_s = SequenceMatcher(None, s_digs, r_digs).ratio() if s_digs else 0.0
                            d_sim = max(sim_c, sim_s)
                            if d_sim >= 0.80:
                                d_near_match = True

                    # Extract prefix part (everything before the digits)
                    p_cand = re.sub(r'\d+$', '', cand_ht_upper or clean_raw_ht)
                    p_roster = re.sub(r'\d+$', '', r_roll)
                    p_sim = SequenceMatcher(None, p_cand, p_roster).ratio() if (p_cand and p_roster) else 0.0

                    if digits_match:
                        # Digits match: score is heavily scaled by how well the prefix matches!
                        ht_score = max(full_sim, 0.45 + 0.50 * p_sim)
                    elif d_near_match and p_sim >= 0.80:
                        # Near-matching roll digits (e.g. single digit OCR handwriting confusion) with matching prefix
                        ht_score = max(full_sim * 0.90, 0.40 + 0.45 * p_sim + 0.15 * d_sim)
                    else:
                        # Non-matching roll digits: heavily penalize HT score to prevent name fuzzy-matching from hijacking rolls
                        ht_score = min(full_sim * 0.35, 0.30)

            # --- Dimension 2: Candidate Name Matching Score (0.0 to 1.0) ---
            # Pillar 4: Windowed root-name matching, initial-expansion aliasing, and cursive OCR tolerance
            name_score = 0.0
            if r_name and has_cand_name:
                s1 = SequenceMatcher(None, clean_name, r_name).ratio()
                s2 = SequenceMatcher(None, name_nospace, rn_nospace).ratio()
                s3 = SequenceMatcher(None, cand_name_upper, r_name).ratio()
                c_sorted = " ".join(sorted(c_parts))
                r_sorted = " ".join(sorted(r_parts))
                s_sort = SequenceMatcher(None, c_sorted, r_sorted).ratio()
                base_sim = max(s1, s2, s3, s_sort)

                # Check Indian Name order independence (Initial(s) + Given Name vs Given Name + Initial(s))
                c_inits = set(w for w in c_parts if len(w) <= 2)
                c_names = [w for w in c_parts if len(w) > 2]
                r_inits = set(w for w in r_parts if len(w) <= 2)
                r_names = [w for w in r_parts if len(w) > 2]
                
                inits_match = (c_inits == r_inits) if (c_inits and r_inits) else False
                if inits_match and c_names and r_names:
                    c_str = " ".join(c_names)
                    r_str = " ".join(r_names)
                    gn_sim = SequenceMatcher(None, c_str, r_str).ratio()
                    if gn_sim >= 0.80:
                        name_score = max(base_sim, 0.90 + gn_sim * 0.09)

                if set(c_parts) == set(r_parts) and len(c_parts) >= 2:
                    name_score = 1.0

                if name_score == 0.0:
                    # Initial check (e.g. 'B' matches 'B' or 'BANGI')
                    initial_match = False
                    if c_parts and r_parts and c_parts[0][0] == r_parts[0][0]:
                        initial_match = True
                    elif name_nospace and rn_nospace and name_nospace[0] == rn_nospace[0]:
                        initial_match = True

                    main_c = c_parts[-1] if c_parts else name_nospace
                    main_r = r_parts[-1] if r_parts else rn_nospace

                    # Ligature & cursive character normalization (e.g. 'EVRL' / 'OEVR' vs 'DEVI')
                    sub_c = re.sub(r'OE', 'D', main_c)
                    sub_c = re.sub(r'[RL]$', 'I', sub_c)
                    main_sim = max(
                        SequenceMatcher(None, main_c, main_r).ratio(),
                        SequenceMatcher(None, sub_c, main_r).ratio()
                    )

                    # If candidate was extracted as a single continuous token (e.g. 'BOEVR') and roster has initial + name:
                    if len(c_parts) <= 1 and initial_match and len(r_parts) >= 2:
                        rem_c = name_nospace[1:]
                        sub_rem = re.sub(r'OE', 'D', rem_c)
                        sub_rem = re.sub(r'[RL]$', 'I', sub_rem)
                        rem_sim = max(
                            SequenceMatcher(None, rem_c, main_r).ratio(),
                            SequenceMatcher(None, sub_rem, main_r).ratio()
                        )
                        main_sim = max(main_sim, rem_sim)

                    # Windowed root-name search for long given names (>= 8 chars, e.g. 'MALLIKARJUNA')
                    long_r_words = [w for w in r_parts if len(w) >= 8]
                    best_long_sim = 0.0
                    for rw in long_r_words:
                        len_rw = len(rw)
                        for w in range(max(4, len_rw - 3), min(len(name_nospace) + 1, len_rw + 4)):
                            for i in range(len(name_nospace) - w + 1):
                                sub = name_nospace[i:i+w]
                                sim = SequenceMatcher(None, sub, rw).ratio()
                                if sim > best_long_sim:
                                    best_long_sim = sim

                    is_multi = len(c_parts) > 2 or len(r_parts) > 2
                    mid_sim = 0.0
                    if is_multi:
                        c_mid = " ".join(c_parts[1:-1])
                        r_mid = " ".join(r_parts[1:-1])
                        mid_sim = SequenceMatcher(None, c_mid, r_mid).ratio() if (c_mid and r_mid) else 0.0

                    if initial_match and main_sim >= 0.65 and (not is_multi or mid_sim >= 0.50):
                        # Direct or ligature-normalized given name match (e.g. 'B EVRL' / 'BOEVR' vs 'B DEVI')
                        name_score = max(base_sim, 0.85 + main_sim * 0.14)
                    elif initial_match and best_long_sim >= 0.65 and (not is_multi or mid_sim >= 0.50 or base_sim >= 0.60):
                        # Long given name windowed match (e.g. 'MALLIKARJUNA' in 'BAUNIC LUNAMAZLIKAA')
                        name_score = max(base_sim, 0.75 + best_long_sim * 0.22)
                    elif main_sim < 0.50 and len(c_parts) >= 2 and len(r_parts) >= 2 and base_sim < 0.60:
                        # Sharing initial but totally different given name -> penalize
                        name_score = base_sim * 0.40
                    else:
                        name_score = base_sim

            # Pillar 2: Center/District Scoped Search affinity
            dist_bonus = 0.0
            if has_cand_ht and pref_dist and r_roll.startswith(pref_dist):
                dist_bonus = 0.02

            # --- Dimension 3: Dual-Signal Weighted Combination ---
            if has_cand_ht and r_roll and has_cand_name and r_name:
                if ht_score >= 0.98 and name_score >= 0.50:
                    total_score = 1.0
                elif ht_score >= 0.98 and name_score < 0.35:
                    # HT matches exactly but Name is completely different student -> penalize collision!
                    total_score = 0.45 * ht_score + 0.55 * name_score
                elif ht_score >= 0.85 and name_score >= 0.70:
                    total_score = max(0.98, 0.55 * ht_score + 0.45 * name_score)
                else:
                    total_score = 0.60 * ht_score + 0.40 * name_score
            elif has_cand_ht and r_roll:
                if has_cand_name:
                    total_score = ht_score * 0.85
                else:
                    total_score = ht_score
            elif has_cand_name and r_name:
                total_score = name_score
            else:
                total_score = 0.0

            total_score += dist_bonus

            if total_score > best_score:
                best_score = total_score
                best_match = record

        if best_match and best_score >= 0.65:
            return best_match.get("roll"), best_match.get("name")
        return None, None

    def resolve_identity_vote(self, dyn_ht, dyn_name, fixed_ht, fixed_name,
                              roster=None, preferred_prefix=None):
        """Pick between the dynamic and fixed identity readings.

        Both readers OCR the same sheet and can disagree (348819:
        dynamic read 'KKD2025K7300694', fixed read 'KKD2025KTS00627';
        the sheet says KKD2025KTS01627). When they disagree, the roster
        decides: the reading whose hall ticket AND name both match a
        roster student wins. Without a roster, or when neither reading
        matches a roster student, the dynamic reading stands (it is the
        mode the user chose, and it is the only one that works on
        shifted sheets like img0076).

        Returns (ht, name, source) with source "dynamic" or "fixed".
        The returned hall ticket / name are the roster-reconciled
        values when the roster matched, else the raw reading.
        """
        from difflib import SequenceMatcher

        dyn_ht = (dyn_ht or "").strip()
        dyn_name = (dyn_name or "").strip()
        fixed_ht = (fixed_ht or "").strip()
        fixed_name = (fixed_name or "").strip()

        def _name_sim(a, b):
            a = re.sub(r"\s+", "", (a or "").upper())
            b = re.sub(r"\s+", "", (b or "").upper())
            if not a or not b:
                return 0.0
            return SequenceMatcher(None, a, b).ratio()

        def _reconciled(cand_ht, cand_name):
            if not roster or (not cand_ht and not cand_name):
                return (None, None)
            try:
                return self._reconcile_with_roster(
                    cand_ht, cand_name, cand_ht, roster,
                    preferred_prefix=preferred_prefix)
            except Exception:
                return (None, None)

        def _win_score(rec, cand_ht, cand_name):
            """How strongly this reading matches a roster student whose
            name matches the sheet's own name read (0.0 = no win)."""
            r_ht, r_name = rec
            if not r_ht or not r_name:
                return 0.0
            if not cand_name:
                # No name on the sheet: only an exact HT match counts.
                return 1.0 if r_ht == cand_ht else 0.0
            sim = _name_sim(cand_name, r_name)
            return sim if sim >= 0.60 else 0.0

        dyn_rec = _reconciled(dyn_ht, dyn_name)
        fixed_rec = _reconciled(fixed_ht, fixed_name)
        dyn_final = (dyn_rec[0] or dyn_ht, dyn_rec[1] or dyn_name)
        fixed_final = (fixed_rec[0] or fixed_ht, fixed_rec[1] or fixed_name)

        if dyn_ht and fixed_ht and dyn_ht == fixed_ht:
            return dyn_final[0], dyn_final[1], "dynamic"
        if dyn_ht and not fixed_ht:
            return dyn_final[0], dyn_final[1], "dynamic"
        if fixed_ht and not dyn_ht:
            # Dynamic found a name but no hall ticket: the name-only
            # reconciliation may already have found the student.
            if dyn_rec[0]:
                return dyn_final[0], dyn_final[1], "dynamic"
            if _win_score(fixed_rec, fixed_ht,
                          fixed_name or dyn_name) > 0:
                return fixed_final[0], fixed_final[1], "fixed"
            return dyn_final[0], dyn_final[1], "dynamic"
        if not dyn_ht and not fixed_ht:
            return dyn_final[0], dyn_final[1], "dynamic"

        dyn_score = _win_score(dyn_rec, dyn_ht, dyn_name)
        fixed_score = _win_score(fixed_rec, fixed_ht, fixed_name)
        if fixed_score > dyn_score:
            return fixed_final[0], fixed_final[1], "fixed"
        return dyn_final[0], dyn_final[1], "dynamic"

    def recognize_hall_ticket(self, image_bgr: np.ndarray, exam_prefix: Optional[str] = None) -> Tuple[str, float, bool]:
        """Recognizes student Hall Ticket Number from character field."""
        ht, name, conf, is_valid = self.extract_identity(image_bgr, exam_prefix=exam_prefix)
        return ht, conf, is_valid

    def recognize_candidate_name(self, image_bgr: np.ndarray) -> Tuple[str, float]:
        """Recognizes student Candidate Name from the name field strip."""
        ht, name, conf, is_valid = self.extract_identity(image_bgr)
        return name, conf


# Global OCR engine instance
ocr_engine = OCREngine()
