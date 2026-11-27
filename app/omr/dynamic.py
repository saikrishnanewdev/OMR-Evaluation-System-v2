"""Dynamic OMR extraction — no layout, no fixed coordinates.

Sai's idea, from the real Syam sheet:
  * Hall ticket / name: a label on the left ("Hall Ticket Number",
    "Name of the Candidate"), and a row of small square boxes on the
    SAME horizontal line to the right. One capital letter per box.
    Find the label, go right on that line, read the boxes.
  * Bubbles: each row starts with a question number, then 4 circles
    to the right on the same line. Find the number, go right on that
    line, find the 4 circles, check which one is filled.

The key PDF is only used for the expected question count (and the
answers). It never tells us where anything is on the sheet.

Everything here works in *relative* units (fractions of the image
size, or multiples of the detected box / circle size). There are no
hardcoded x/y positions for any field. The existing fixed-template
code stays untouched as a fallback — see EvaluationService.

Detection notes (from the Syam photos):
  * Labels, box outlines and bubble outlines are printed in pink/red.
    Student writing and filled bubbles are dark (blue/black pen).
    So a "redness" mask (red channel clearly above green/blue)
    finds the printed form, and the ink map (255 - red, as in
    Preprocessor.extract_ink_channel) finds the student's marks.
  * Boxes in a row touch each other, so they appear as one long
    rectangle with vertical dividers — not as separate contours.
    We therefore detect the long row rectangle, then split it into
    square boxes using its own height (boxes are square).
  * Empty bubbles still contain a small printed 1/2/3/4, so fill is
    judged from the *centre* of each circle only, not from the whole
    circle.
  * Above the ANSWERS section there are other bubbles (Booklet Code
    A-D, Booklet Number). They are ignored: bubble search only runs
    below the "ANSWERS" heading, or below the top third of the page
    when the heading is not found.
"""

import re
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.config.constants import (
    BUBBLE_RADIUS,
    FILL_AMBIGUOUS_MAX_RATIO,
    FILL_BLANK_THRESHOLD,
    FILL_MARKED_THRESHOLD,
    FILL_RATIO_MIN,
    OPTION_NAMES,
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def redness_mask(image_bgr: np.ndarray) -> np.ndarray:
    """Binary mask of pink/red printed form lines/text.

    Pink/red ink has a red channel clearly above green and blue;
    white paper has all channels high and similar, dark pen ink has
    all channels low. Returns a uint8 mask (255 = red form ink).
    """
    b, g, r = cv2.split(image_bgr)
    r_i = r.astype(np.int16)
    g_i = g.astype(np.int16)
    b_i = b.astype(np.int16)
    mask = ((r_i - g_i > 18) & (r_i - b_i > 10) & (r_i > 90)).astype(np.uint8) * 255
    return mask


def ink_map(image_bgr: np.ndarray) -> np.ndarray:
    """Same ink channel as Preprocessor.extract_ink_channel: 255 - red."""
    _, _, r = cv2.split(image_bgr)
    return (255 - r).astype(np.float32)


def _median(values: List[float], default: float = 0.0) -> float:
    if not values:
        return default
    return float(np.median(values))


# ---------------------------------------------------------------------------
# Box rows (hall ticket / name / gender / ...)
# ---------------------------------------------------------------------------

@dataclass
class BoxRow:
    """One horizontal row of square character boxes."""
    y: int                      # centre y of the row
    y1: int
    y2: int
    x1: int
    x2: int
    box_w: float                # width of one square box
    box_h: float
    num_boxes: int
    boxes: List[Tuple[int, int, int, int]] = field(default_factory=list)
    # boxes: list of (x, y, w, h) per character box, left to right

    @property
    def height(self) -> float:
        return float(self.y2 - self.y1)


def _row_boxes(mask: np.ndarray, x: int, y: int, bw: int, bh: int):
    """Box count and box rects for a row rect, from its vertical dividers.

    Returns (n, boxes); n < 4 means 'not a box row'. The dividers
    are counted exactly from the red columns inside the row, not
    from width/height — the printed stroke inflates the height a
    little and width/height alone undercounts by one on some sheets.
    """
    col_sum = mask[y:y + bh, x:x + bw].sum(axis=0) / 255.0
    above = col_sum > bh * 0.6
    dividers = 0
    in_line = False
    for v in above:
        if v and not in_line:
            dividers += 1
            in_line = True
        elif not v:
            in_line = False
    n = dividers - 1 if dividers >= 5 else int(round(bw / float(bh)))
    if n < 4:
        return 0, []
    box_w = bw / float(n)
    boxes = []
    for i in range(n):
        bx = int(round(x + i * box_w))
        bx2 = int(round(x + (i + 1) * box_w))
        boxes.append((bx, y, max(1, bx2 - bx), bh))
    return n, boxes


def _split_tall_strip(mask: np.ndarray, x: int, y: int, bw: int,
                     bh: int) -> List[Tuple[int, int]]:
    """Split a too-tall red strip into its box-row bands.

    Several box rows joined by a vertical red line (150Q sheet: the
    name row is joined to the gender/community rows, and to the top
    of the answer block) form one tall contour that the row finder
    would reject outright. A row band is a run of y where the red
    spans most of the strip width (box dividers and row edges);
    between rows only the thin vertical line is red, so the red
    spans a few pixels. Returns [(y1, y2), ...] bands.
    """
    sub = mask[y:y + bh, x:x + bw]
    spread = np.zeros(bh, dtype=int)
    for i in range(bh):
        xs = np.flatnonzero(sub[i] > 0)
        if len(xs):
            spread[i] = int(xs[-1] - xs[0])
    gap = spread < max(8.0, 0.10 * bw)
    bands: List[Tuple[int, int]] = []
    i = 0
    while i < bh:
        if gap[i]:
            i += 1
            continue
        j = i
        while j < bh and not gap[j]:
            j += 1
        bands.append((y + i, y + j))
        i = j
    return bands


def _row_from_band(mask: np.ndarray, x: int, y: int, bw: int, bh: int,
                   page_w: int, min_h: float, max_h: float):
    """A BoxRow for one band split from a tall strip, or None.

    The band is narrower than the strip (the gender row is 5 boxes
    wide while the strip spans the whole name row), so its
    horizontal extent is recomputed from the mask inside the band.
    The usual row checks (height, width, box count) still apply, so
    text lines and answer-block bands are rejected.
    """
    if bh < min_h or bh > max_h:
        return None
    sub = mask[y:y + bh, x:x + bw]
    col_sum = sub.sum(axis=0) / 255.0
    xs = np.flatnonzero(col_sum > bh * 0.3)
    if len(xs) == 0:
        return None
    x1 = x + int(xs[0])
    x2 = x + int(xs[-1]) + 1
    bw2 = x2 - x1
    if bw2 < bh * 4 or bw2 < page_w * 0.08:
        return None
    n, boxes = _row_boxes(mask, x1, y, bw2, bh)
    if n < 4:
        return None
    return BoxRow(y=y + bh // 2, y1=y, y2=y + bh, x1=x1, x2=x2,
                  box_w=bw2 / float(n), box_h=float(bh), num_boxes=n,
                  boxes=boxes)


def find_box_rows(image_bgr: np.ndarray,
                  top_fraction: float = 0.45) -> List[BoxRow]:
    """Find every row of square character boxes in the top of the sheet.

    Returns rows sorted top-to-bottom. Each row is a long thin
    rectangle (the joined boxes) split into square boxes using its
    own height. Rows with fewer than 4 boxes are ignored.
    """
    h, w = image_bgr.shape[:2]
    limit_y = int(h * top_fraction)
    mask = redness_mask(image_bgr[:limit_y])

    # Close small gaps in the printed outlines so each row becomes
    # one solid strip, then find its outer contour.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)

    rows: List[BoxRow] = []
    min_h = max(6.0, h * 0.006)
    max_h = h * 0.045
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bh < min_h:
            continue
        if bh > max_h:
            # Several box rows joined by a vertical red line (150Q
            # sheet: the name row is joined to the gender/community
            # rows). Split the tall strip at the horizontal gaps
            # between rows and build a row per band, instead of
            # rejecting the whole strip (which loses the name row).
            for (by1, by2) in _split_tall_strip(mask, x, y, bw, bh):
                row = _row_from_band(mask, x, by1, bw, by2 - by1,
                                     w, min_h, max_h)
                if row is not None:
                    rows.append(row)
            continue
        if bw < bh * 4:      # a box row is much wider than it is tall
            continue
        if bw < w * 0.08:
            continue
        # Boxes are square, so one box is ~ as wide as the row is tall.
        # Count them exactly from the vertical dividers inside the row
        # (columns that are red for most of the row height), not from
        # width/height — the printed stroke inflates the height a little
        # and width/height alone undercounts by one on some sheets.
        n, boxes = _row_boxes(mask, x, y, bw, bh)
        if n < 4:
            continue
        box_w = bw / float(n)
        rows.append(BoxRow(y=y + bh // 2, y1=y, y2=y + bh, x1=x, x2=x + bw,
                           box_w=box_w, box_h=float(bh), num_boxes=n,
                           boxes=boxes))
    rows.sort(key=lambda r: r.y)
    # Merge duplicate detections of the same row (overlapping y).
    merged: List[BoxRow] = []
    for row in rows:
        if merged and abs(row.y - merged[-1].y) < merged[-1].box_h * 0.6:
            if row.num_boxes > merged[-1].num_boxes:
                merged[-1] = row
            continue
        merged.append(row)
    return merged


def top_is_cut_off(image_bgr: np.ndarray) -> bool:
    """True when the top of the page looks cut off in this image.

    The track-warped alignment can push the hall-ticket row above
    y=0 when the timing track is only partially detected (200Q Syam
    sheet: first detected mark far below the real top of the track).
    What remains is a box row sliver touching the top edge (y1 == 0)
    — a real box row never starts at the very top of the page.
    Callers use this to switch dynamic detection to a deskewed-only
    copy of the raw scan, where the whole page stays in frame.
    """
    try:
        rows = find_box_rows(image_bgr)
    except Exception:
        return False
    return any(r.y1 <= 2 for r in rows)


def _normalise_text(text: str) -> str:
    return re.sub(r"[^a-z ]", " ", text.lower()).strip()


def find_labels(image_bgr: np.ndarray,
                ocr_engine=None) -> List[Dict]:
    """Find printed label texts on the sheet, if an OCR engine is given.

    Uses the RapidOCR engine already wrapped by app.ocr.engine.OCREngine
    (its ``.ocr`` callable returns [box, text, score] triples).
    Returns [{'text': ..., 'cx': ..., 'cy': ..., 'x2': ...}] sorted by y.
    Returns [] when no OCR engine is available — callers fall back to
    row order instead of failing.
    """
    if ocr_engine is None:
        return []
    try:
        rapid = getattr(ocr_engine, "ocr", None)
        if rapid is None:
            return []
        result, _ = rapid(image_bgr)
    except Exception:
        return []
    labels: List[Dict] = []
    if not result:
        return labels
    for item in result:
        try:
            box, text, _score = item[0], item[1], item[2]
        except Exception:
            continue
        if not text or not text.strip():
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        labels.append({
            "text": text.strip(),
            "norm": _normalise_text(text),
            "cx": float(sum(xs) / len(xs)),
            "cy": float(sum(ys) / len(ys)),
            "x1": float(min(xs)),
            "x2": float(max(xs)),
            "y1": float(min(ys)),
            "y2": float(max(ys)),
        })
    labels.sort(key=lambda d: d["cy"])
    return labels


def _row_for_label(rows: List[BoxRow], labels: List[Dict],
                   *needles: str) -> Optional[BoxRow]:
    """The box row on the same horizontal line as a label.

    A row matches when its centre y is within ~1.5 box heights of the
    label centre y, and the row starts to the right of the label.
    Spaces are ignored on both sides: RapidOCR sometimes returns a
    label as one word ('HALLTICKETNUMBER' on the 150Q sheet) and
    sometimes as separate words ('HALL TICKET NUMBER' on the 200Q
    sheet), and the match must not depend on that.
    """
    for lab in labels:
        lab_norm = lab["norm"].replace(" ", "")
        if not any(n.replace(" ", "") in lab_norm for n in needles):
            continue
        best: Optional[BoxRow] = None
        best_dy = 1e9
        for row in rows:
            if row.x1 < lab["x2"] - row.box_w:
                continue
            dy = abs(row.y - lab["cy"])
            if dy <= max(1.5 * row.box_h, 12.0) and dy < best_dy:
                best, best_dy = row, dy
        if best is not None:
            return best
    return None


# ---------------------------------------------------------------------------
# Reading a box row (hall ticket / name)
# ---------------------------------------------------------------------------

def _row_strip_images(image_bgr: np.ndarray, row: BoxRow,
                      ocr_engine=None):
    """Raw + cleaned strip images for one box row.

    Raw is the row as cropped from the image; cleaned is the same
    strip after the OCREngine cleaning (red dropout, 2.5x zoom, white
    padding) — the images the review UI shows as the ht/name crops.
    Returns (None, None) when the row has no pixels.
    """
    raw = image_bgr[max(0, row.y1 - 2):row.y2 + 2,
                    max(0, row.x1 - 2):row.x2 + 2]
    if raw.size == 0:
        return None, None
    strip = raw
    remove_red = getattr(ocr_engine, "remove_red_color", None) if ocr_engine else None
    if remove_red is not None:
        strip = remove_red(strip)
    zoomed = cv2.resize(strip, None, fx=2.5, fy=2.5,
                        interpolation=cv2.INTER_CUBIC)
    pad = cv2.copyMakeBorder(zoomed, 15, 15, 30, 30,
                             cv2.BORDER_CONSTANT, value=[255, 255, 255])
    return raw, pad


def identity_crops(image_bgr: np.ndarray, identity: "DynamicIdentity",
                   ocr_engine=None) -> Dict:
    """Crop images for a dynamic identity, in the same shape as the
    fixed reader's crops dict (ht_processed, name_processed, ht_raw,
    name_raw, ht_missing_on_sheet), so callers can display them the
    same way. A missing row yields a blank white placeholder image.
    """
    crops: Dict = {"ht_missing_on_sheet": False}
    for key, row in (("ht", identity.hall_ticket_row),
                     ("name", identity.name_row)):
        blank = np.full((50, 200, 3), 255, dtype=np.uint8)
        if row is None:
            crops[f"{key}_raw"] = blank
            crops[f"{key}_processed"] = blank
            if key == "ht":
                crops["ht_missing_on_sheet"] = True
            continue
        raw, pad = _row_strip_images(image_bgr, row, ocr_engine)
        crops[f"{key}_raw"] = raw if raw is not None else blank
        crops[f"{key}_processed"] = pad if pad is not None else blank
    return crops


# A box counts as filled when it holds enough dark pen ink.
# Calibrated on the real paths (200Q Syam sheet on the deskewed copy,
# 160Q sample on the warped copy; ink > 60, 4 px inset from the box
# edges): filled boxes scored 61+, empty boxes 41 or less.
FILLED_BOX_MIN_INK = 45


def _filled_box_span(image_bgr: np.ndarray, row: BoxRow):
    """(first, last) index of the filled boxes in a box row, or None.

    Students write left to right, so the text sits in one run of
    filled boxes. The empty boxes after it must not be read: after
    red dropout they still leave faint edges, and the recogniser
    invents letters from them — the '1ZGG' / 'TDODLD' ghost tail
    after a clean hall ticket / name. Returns None when no box is
    filled (a blank field) or the row has no box list.
    """
    if not row.boxes:
        return None
    ink = ink_map(image_bgr)
    filled = []
    for i, (bx, by, bw, bh) in enumerate(row.boxes):
        x1 = max(0, bx + 4)
        x2 = min(ink.shape[1], bx + bw - 4)
        y1 = max(0, by + 4)
        y2 = min(ink.shape[0], by + bh - 4)
        patch = ink[y1:y2, x1:x2]
        count = int((patch > 60).sum()) if patch.size else 0
        if count >= FILLED_BOX_MIN_INK:
            filled.append(i)
    if not filled:
        return None
    return filled[0], filled[-1]


# Characters RapidOCR confuses, from OCREngine.CHAR_TO_DIGIT (letters
# it reads as digits) and its digit_to_letter reverse.
_LETTER_TO_DIGIT = {
    "O": "0", "D": "0", "Q": "0", "U": "0",
    "I": "1", "J": "1", "L": "1",
    "Z": "2", "E": "3", "A": "4", "S": "5",
    "G": "6", "T": "7", "B": "8", "g": "9",
}


def _looks_like(a: str, b: str) -> bool:
    """True when a and b are the same character or a known look-alike."""
    if a == b:
        return True
    return (_LETTER_TO_DIGIT.get(a) == b
            or _LETTER_TO_DIGIT.get(b) == a)


def correct_hall_ticket(text: str, prefix: Optional[str] = None,
                        expected_len: Optional[int] = None) -> str:
    """Fix look-alike misreads in a hall ticket.

    With a trustworthy prefix (roster / batch / user-supplied exam
    prefix): a character that differs from the prefix only by a
    look-alike is replaced by the prefix character, and letters
    after the prefix (the roll number) become digits. The prefix is
    only trusted when every overlapping character matches it or
    looks like it — a mismatched prefix is ignored, never applied,
    so a wrong roster/batch prefix cannot corrupt the reading.
    Without a prefix, only the safe trailing rule applies: letters
    after the final digit run are digits (the fixed code already
    did this for batch prefixes).

    expected_len is the number of filled boxes in the row (one
    character per box). When the text is exactly one character
    short and the last prefix character was read as a digit that
    looks like it (handwritten J + 1 fused into a single '1'), that
    digit does double duty: it is both the prefix letter and the
    first roll digit, so it is restored at the start of the roll.
    """
    if not text:
        return text
    text = text.upper()
    if prefix:
        prefix = prefix.upper().strip()
        n = min(len(prefix), len(text))
        if n >= 4 and all(_looks_like(text[i], prefix[i])
                          for i in range(n)):
            chars = list(text)
            for i in range(n):
                chars[i] = prefix[i]
            roll = chars[n:]
            if (expected_len is not None
                    and expected_len - len(text) == 1
                    and n > 0
                    and text[n - 1].isdigit()
                    and prefix[n - 1].isalpha()):
                # Merged boundary character (see docstring).
                roll = [text[n - 1]] + roll
            for i, c in enumerate(roll):
                roll[i] = _LETTER_TO_DIGIT.get(c, c)
            return "".join(chars[:n] + roll)
    chars = list(text)
    i = len(chars) - 1
    while i >= 0 and chars[i].isalpha() and chars[i] in _LETTER_TO_DIGIT:
        if any(c.isdigit() for c in chars[:i]):
            chars[i] = _LETTER_TO_DIGIT[chars[i]]
            i -= 1
        else:
            break
    return "".join(chars)


def _recognise_strip(pad: np.ndarray, ocr_engine) -> str:
    """Run RapidOCR's text recogniser on a prepared strip image.

    The strip is height-normalised to 48px first (the recogniser
    expects a fixed-height input); returns "" on any failure.
    """
    if pad is None or ocr_engine is None:
        return ""
    try:
        h, w = pad.shape[:2]
        if h == 0 or w == 0:
            return ""
        scaled = cv2.resize(pad, (int(w * 48.0 / h), 48),
                            interpolation=cv2.INTER_AREA)
        recogniser = getattr(ocr_engine, "ocr", None)
        if recogniser is None:
            return ""
        preds, _ = recogniser.text_recognizer([scaled])
        if preds and preds[0] and preds[0][0]:
            return str(preds[0][0]).strip()
    except Exception:
        return ""
    return ""


def read_box_row_strip(image_bgr: np.ndarray, row: BoxRow,
                       ocr_engine=None, expand_bottom: float = 0.0) -> str:
    """Read the handwriting in one box row using the existing OCR engine.

    Crops the row to the filled boxes only, removes the red printed
    lines and zooms 2.5x first — the same cleaning OCREngine uses for
    its fixed strips — then runs the strip through RapidOCR's text
    recogniser. Returns "" when no OCR engine is available.

    expand_bottom stretches the strip downward by that fraction of
    the row height before reading. Handwriting can dip below the
    detected row (the row is found from the red box lines, but the
    ink sits low in the boxes), and the taller strip reads it: on
    OMR_348819 the normal strip reads 'KKD2025K7300694' while the
    strip with expand_bottom=0.25 reads 'KKD2025KTS01624', which the
    roster corrects to the true 'KKD2025KTS01627'. The primary read
    keeps expand_bottom=0.0 — the taller strip is only a second
    opinion, because on some sheets (img0076) it reads worse.
    """
    if ocr_engine is None:
        return ""
    try:
        span = _filled_box_span(image_bgr, row)
        if span is None:
            # No filled box: blank field (or a row without a box list
            # falls through to the whole-row read below).
            if row.boxes:
                return ""
        else:
            first, last = span
            row = replace(
                row,
                x1=row.boxes[first][0],
                x2=row.boxes[last][0] + row.boxes[last][2])
        if expand_bottom:
            pad = int(round((row.y2 - row.y1) * expand_bottom))
            if pad > 0:
                row = replace(row, y2=row.y2 + pad)
        _raw, pad = _row_strip_images(image_bgr, row, ocr_engine)
        return _recognise_strip(pad, ocr_engine)
    except Exception:
        return ""
    return ""


def read_box_row_strip_candidates(image_bgr: np.ndarray, row: BoxRow,
                                  ocr_engine=None) -> List[str]:
    """All readings of one box row, best (red-drop) first.

    The same strip is read three ways, because no single cleaning
    wins on every handwriting: (1) red-drop — the current reading,
    best on most sheets; (2) ink-binary — the ink map (255 - R)
    thresholded at 120, which reads clean block capitals the
    red-drop smears (PRIYA's name reads 'PRIVA' here, 0.8 similar
    to the roster, vs 'PRHNA', 0.6, red-drop); (3) raw — no red
    removal at all. Duplicates and empty readings are dropped.
    Callers try them in order and keep the first that reconciles
    against the roster, so the current behaviour is unchanged when
    the red-drop reading already matches.
    """
    if ocr_engine is None or row is None:
        return []
    try:
        span = _filled_box_span(image_bgr, row)
        if span is None:
            if row.boxes:
                return []
        else:
            first, last = span
            row = replace(
                row,
                x1=row.boxes[first][0],
                x2=row.boxes[last][0] + row.boxes[last][2])
        raw, pad = _row_strip_images(image_bgr, row, ocr_engine)
        if raw is None or pad is None:
            return []
        out: List[str] = []
        for text in (_recognise_strip(pad, ocr_engine),
                     _recognise_strip(_ink_binary_strip(raw), ocr_engine),
                     _recognise_strip(_zoom_pad(raw), ocr_engine)):
            if text and text not in out:
                out.append(text)
        return out
    except Exception:
        return []


def _ink_binary_strip(raw: np.ndarray) -> np.ndarray:
    """Ink-binary version of a raw strip: the ink map (255 - R)
    thresholded at 120, as a white-background 3-channel image at
    the same 2.5x zoom + padding as the red-drop strip."""
    ink = ink_map(raw)
    binary = np.where(ink > 120, 0, 255).astype(np.uint8)
    binary = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    return _zoom_pad(binary)


def _zoom_pad(strip: np.ndarray) -> np.ndarray:
    """2.5x zoom + white padding, matching _row_strip_images."""
    zoomed = cv2.resize(strip, None, fx=2.5, fy=2.5,
                        interpolation=cv2.INTER_CUBIC)
    return cv2.copyMakeBorder(zoomed, 15, 15, 30, 30,
                              cv2.BORDER_CONSTANT, value=[255, 255, 255])


@dataclass
class DynamicIdentity:
    hall_ticket: str = ""
    name: str = ""
    confidence: float = 0.0
    method: str = ""            # "label" | "row-order" | "none"
    hall_ticket_row: Optional[BoxRow] = None
    name_row: Optional[BoxRow] = None
    # Alternate readings of the name strip (red-drop first, then
    # ink-binary, then raw — see read_box_row_strip_candidates).
    # The primary name is the first of these; callers try the rest
    # only when the primary does not reconcile against the roster.
    name_candidates: List[str] = field(default_factory=list)
    # Second reading of the hall-ticket row, from a taller strip
    # (see read_box_row_strip's expand_bottom). A second opinion on
    # the same row, used by the identity vote: when the two readings
    # disagree, the roster decides. Empty when it agrees with the
    # primary reading (or when there is no hall-ticket row).
    hall_ticket_alt: str = ""


def extract_identity_dynamic(image_bgr: np.ndarray,
                             ocr_engine=None,
                             exam_prefix: Optional[str] = None,
                             labels: Optional[List[Dict]] = None
                             ) -> DynamicIdentity:
    """Find hall ticket + name without any fixed coordinates.

    1. Find all box rows in the top of the sheet.
    2. If OCR is available, find the "Hall Ticket Number" and
       "Name of the Candidate" labels and take the box row on the
       same line as each label.
    3. Otherwise fall back to row order: the first two long rows
       (>= 8 boxes) in the top area are hall ticket, then name.
       (Gender has few boxes; Community/District come after.)
    4. Read each chosen row with the OCR engine, if available.

    `labels`, when given, is the full-page OCR result already
    computed by the caller (analyze_sheet_dynamic) — it is reused
    here instead of running the slow full-page OCR a second time.
    """
    rows = find_box_rows(image_bgr)
    if labels is None:
        labels = find_labels(image_bgr, ocr_engine=ocr_engine)

    ht_row = _row_for_label(rows, labels, "hall ticket")
    name_row = _row_for_label(rows, labels, "name of the candidate",
                              "name of candidate")
    method = "label" if (ht_row is not None or name_row is not None) else ""

    if ht_row is None or name_row is None:
        long_rows = [r for r in rows if r.num_boxes >= 8]
        if ht_row is None and len(long_rows) >= 1:
            ht_row = long_rows[0]
        if name_row is None and len(long_rows) >= 2:
            # Name is the next long row after the hall ticket row.
            after = [r for r in long_rows if r is not ht_row and r.y > ht_row.y]
            if after:
                name_row = after[0]
        if method == "":
            method = "row-order" if (ht_row is not None or name_row is not None) else "none"

    ht_text = read_box_row_strip(image_bgr, ht_row, ocr_engine) if ht_row else ""
    name_text = read_box_row_strip(image_bgr, name_row, ocr_engine) if name_row else ""
    name_candidates = (read_box_row_strip_candidates(image_bgr, name_row, ocr_engine)
                       if name_row else [])

    # Same cleaning as OCREngine: keep only letters/digits, upper case.
    ht_clean = re.sub(r"[^A-Za-z0-9]", "", ht_text).upper()
    name_clean = re.sub(r"[^A-Za-z ]", " ", name_text).upper()
    name_clean = " ".join(name_clean.split())
    name_cands_clean = []
    for cand in name_candidates:
        c = re.sub(r"[^A-Za-z ]", " ", cand).upper()
        c = " ".join(c.split())
        if c and c not in name_cands_clean:
            name_cands_clean.append(c)
    if name_clean and name_clean not in name_cands_clean:
        name_cands_clean.insert(0, name_clean)
    elif not name_clean and name_cands_clean:
        name_clean = name_cands_clean[0]
    # The filled-box count is the true character count (one
    # character per box); it exposes a merged character.
    ht_expected_len = None
    if ht_row is not None:
        span = _filled_box_span(image_bgr, ht_row)
        if span is not None:
            ht_expected_len = span[1] - span[0] + 1
    if ht_clean:
        # Fix look-alike misreads (0/O, 5/S, J/1) against the exam
        # prefix when one is known — a mismatched prefix is ignored.
        ht_clean = correct_hall_ticket(ht_clean, prefix=exam_prefix,
                                       expected_len=ht_expected_len)

    # Second opinion on the same hall-ticket row (taller strip —
    # see read_box_row_strip). Only kept when it differs from the
    # primary reading; the identity vote decides between them.
    ht_alt = ""
    if ht_row is not None and ocr_engine is not None:
        alt_text = read_box_row_strip(image_bgr, ht_row, ocr_engine,
                                      expand_bottom=0.25)
        alt_clean = re.sub(r"[^A-Za-z0-9]", "", alt_text).upper()
        if alt_clean and alt_clean != ht_clean:
            ht_alt = correct_hall_ticket(alt_clean, prefix=exam_prefix,
                                         expected_len=ht_expected_len)

    conf = 0.0
    if ht_clean:
        conf = max(conf, 0.7)
    if name_clean and len(name_clean) >= 3:
        conf = max(conf, 0.7)
    if ht_clean and name_clean:
        conf = 0.9
    return DynamicIdentity(hall_ticket=ht_clean, name=name_clean,
                           confidence=conf, method=method,
                           hall_ticket_row=ht_row, name_row=name_row,
                           name_candidates=name_cands_clean,
                           hall_ticket_alt=ht_alt)


@dataclass
class DailyTestIdentity:
    """Identity from a daily-test (20Q) strip: B No (batch), ID No,
    name. The values are handwritten in a small table at the top
    right — the B No and ID No sit in cells BELOW their labels, not
    beside them — so they are read by targeted label-anchored crops
    (see extract_identity_20q), not by box rows."""
    b_no: str = ""
    id_no: str = ""
    name: str = ""
    b_no_candidates: List[str] = field(default_factory=list)
    id_no_candidates: List[str] = field(default_factory=list)
    name_candidates: List[str] = field(default_factory=list)


def _recognise_crop(raw_crop: np.ndarray, ocr_engine,
                    zoom: float = 2.5) -> str:
    """Read one handwriting crop with the recogniser.

    Red-drops the crop, zooms it (2.5x by default; 4.0x reads the
    short B No cell better on some sheets), pads white, then runs
    the recogniser. The full ocr() detector returns "" on these
    small crops, so the recogniser is called directly.
    """
    if raw_crop is None or raw_crop.size == 0 or ocr_engine is None:
        return ""
    try:
        remove_red = getattr(ocr_engine, "remove_red_color", None)
        strip = remove_red(raw_crop) if remove_red is not None else raw_crop
        zoomed = cv2.resize(strip, None, fx=zoom, fy=zoom,
                            interpolation=cv2.INTER_CUBIC)
        pad = cv2.copyMakeBorder(zoomed, 15, 15, 30, 30,
                                 cv2.BORDER_CONSTANT, value=[255, 255, 255])
        return _recognise_strip(pad, ocr_engine)
    except Exception:
        return ""


def _label_by_norm(labels: List[Dict], *needles: str) -> Optional[Dict]:
    """The first label whose space-stripped norm contains a needle
    ('bno', 'idno', 'nameofthecandidate'). RapidOCR returns the B
    No label as 'BNo.:' on one sheet and 'B No.:' on another, so
    spaces must be ignored — the same rule as _row_for_label."""
    for lab in labels:
        norm = lab["norm"].replace(" ", "")
        if any(n.replace(" ", "") in norm for n in needles):
            return lab
    return None


def extract_identity_20q(image_bgr: np.ndarray,
                         ocr_engine=None) -> DailyTestIdentity:
    """Read B No / ID No / name from a daily-test (20Q) strip.

    The strip has no hall-ticket box row: the name is written in
    boxes right of the 'Name of the Candidate' label, and the B No
    (one wide cell) and ID No (3 digit boxes) sit in cells BELOW
    the 'B No.:' and 'ID No.:' labels at the top right. Each value
    is read from its cell with the recogniser (red-drop; the B No
    and ID No are also read at 4.0x, because neither zoom wins on
    every sheet — LAKSHMAN's 'T9' needs 4.0x, K HYMA's 'T15' needs
    2.5x). The roster matcher tries the candidates in order, so a
    wrong zoom reading cannot win over a right one that matches a
    real student.
    """
    out = DailyTestIdentity()
    if ocr_engine is None:
        return out
    labels = find_labels(image_bgr, ocr_engine=ocr_engine)
    if not labels:
        return out

    name_lab = _label_by_norm(labels, "nameofthecandidate", "name")
    if name_lab is not None:
        x1 = int(name_lab["x2"]) + 2
        x2 = min(image_bgr.shape[1], x1 + 480)
        y1 = max(0, int(name_lab["y1"]) - 4)
        y2 = int(name_lab["y2"]) + 4
        crop = image_bgr[y1:y2, x1:x2]
        cands = []
        for text in (_recognise_crop(crop, ocr_engine, 2.5),
                     _recognise_strip(_ink_binary_strip(crop), ocr_engine),
                     _recognise_crop(crop, ocr_engine, 4.0)):
            c = re.sub(r"[^A-Za-z ]", " ", text).upper()
            c = " ".join(c.split())
            if c and c not in cands:
                cands.append(c)
        if cands:
            out.name = cands[0]
            out.name_candidates = cands

    for key, needle in (("b_no", "bno"), ("id_no", "idno")):
        lab = _label_by_norm(labels, needle)
        if lab is None:
            continue
        # The value cell is directly below the label.
        x1 = max(0, int(lab["x1"]) - 4)
        x2 = int(lab["x2"]) + 4
        y1 = int(lab["y2"]) + 1
        y2 = min(image_bgr.shape[0], y1 + 46)
        crop = image_bgr[y1:y2, x1:x2]
        cands = []
        for text in (_recognise_crop(crop, ocr_engine, 2.5),
                     _recognise_crop(crop, ocr_engine, 4.0)):
            c = re.sub(r"[^A-Za-z0-9]", "", text).upper()
            if c and c not in cands:
                cands.append(c)
        if cands:
            setattr(out, key, cands[0])
            setattr(out, f"{key}_candidates", cands)
    return out


# ---------------------------------------------------------------------------
# Bubbles (question number -> 4 circles on the same line)
# ---------------------------------------------------------------------------

@dataclass
class DynamicBubbleRow:
    question_number: int
    centres: List[Tuple[float, float]]   # 4 circle centres, left to right
    fills: List[float] = field(default_factory=list)
    detected_option: str = "BLANK"
    status: str = "UNATTEMPTED"
    confidence: float = 0.0


def _classify_fills(fills: List[float]) -> Tuple[str, str, float]:
    """Centre fill + dominance ratio: the strongest option wins only
    when it is clearly darker than the rest; two strong options is
    a double mark; none strong is blank."""
    if len(fills) != len(OPTION_NAMES):
        return "BLANK", "UNATTEMPTED", 0.0
    order = sorted(range(len(fills)), key=lambda i: fills[i], reverse=True)
    best, second = order[0], order[1]
    best_fill, second_fill = fills[best], fills[second]
    ratio = best_fill / (second_fill + 1e-4)
    if best_fill < FILL_BLANK_THRESHOLD:
        conf = float(np.clip(1.0 - (best_fill / max(FILL_BLANK_THRESHOLD, 1.0)), 0.5, 1.0))
        return "BLANK", "UNATTEMPTED", conf
    if best_fill >= FILL_MARKED_THRESHOLD and second_fill >= FILL_MARKED_THRESHOLD:
        if ratio >= 1.8:
            return OPTION_NAMES[best], "SINGLE", float(np.clip(1.0 - second_fill / (best_fill + 1e-4), 0.4, 0.95))
        return "MULTI", "MULTI", 0.0
    if best_fill >= FILL_MARKED_THRESHOLD and ratio >= FILL_RATIO_MIN - 0.7:
        return OPTION_NAMES[best], "SINGLE", 0.9
    if ratio >= 1.5 and best_fill >= 45.0:
        return OPTION_NAMES[best], "SINGLE", 0.5
    return "AMBIGUOUS", "AMBIGUOUS", 0.4


def _split_wide_block(mask: np.ndarray, rect: Tuple[int, int, int, int],
                      page_w: int) -> List[Tuple[int, int, int, int]]:
    """Split one wide pink block into its answer columns.

    On the 150Q sheet the three answer columns sit in ONE joined
    pink block (598px wide, 36% of the page), not three separate
    rectangles, so the column finder below would reject the whole
    block and Dynamic would find no bubbles at all. The columns are
    separated by narrow white gaps: the vertical red profile across
    the block dips to ~0.3 at the gaps while the pink columns sit at
    ~0.6. Split at the deep valleys that rise back to pink level on
    both sides. Returns [] when no such valleys exist (the block is
    then dropped, exactly as before).
    """
    x1, y1, x2, y2 = rect
    if x2 - x1 < 60 or y2 - y1 < 10:
        return []
    prof = (mask[y1:y2, x1:x2] > 0).mean(axis=0).astype(float)
    # Smooth a little so a single stray column does not fake a valley.
    k = 11
    pad = np.pad(prof, (k // 2, k // 2), mode="edge")
    sm = np.convolve(pad, np.ones(k) / k, mode="valid")
    level = float(np.median(sm))
    if level <= 0.2:
        return []
    thresh = 0.75 * level
    n = len(sm)
    valleys: List[int] = []
    for i in range(60, n - 60):
        if sm[i] >= thresh:
            continue
        if sm[i] != min(sm[max(0, i - 40):i + 41]):
            continue
        # Must rise back to pink level on both sides: a ramp at the
        # block edge (the question-number strip) is not a valley.
        left = sm[max(0, i - 80):max(0, i - 40)]
        right = sm[i + 40:i + 81]
        if len(left) == 0 or len(right) == 0:
            continue
        if left.max() < thresh or right.max() < thresh:
            continue
        if valleys and i - valleys[-1] < 80:
            if sm[i] < sm[valleys[-1]]:
                valleys[-1] = i
            continue
        valleys.append(i)
    if not valleys:
        return []
    bounds = [x1] + [x1 + v for v in valleys] + [x2]
    out = []
    for a, b in zip(bounds, bounds[1:]):
        if b - a >= 0.05 * page_w:
            out.append((a, y1, b, y2))
    return out if len(out) >= 2 else []


def _rows_per_column(expected_questions: Optional[int],
                     n_cols: int) -> List[int]:
    """How many question rows each answer column holds.

    Questions fill down each column, left to right, so every column
    but the last holds the same count and the last column holds the
    remainder: 50 questions over 4 columns is 13, 13, 13, 11 (the
    50Q grand-test sheet), not 12 each. An exact split gives equal
    counts (200/5 = 40 each, 150/3 = 50 each, 20/4 = 5 each).
    Falls back to 40 per column when no count is given.
    """
    if not expected_questions or n_cols <= 0:
        return [40] * n_cols
    n = int(expected_questions)
    base = -(-n // n_cols)  # ceil(n / n_cols) for the full columns
    rows = [base] * (n_cols - 1)
    rows.append(n - base * (n_cols - 1))
    return rows


def _find_answer_columns(image_bgr: np.ndarray,
                         search_y1: int) -> List[Tuple[int, int, int, int]]:
    """Find the large pink answer-column rectangles below search_y1.

    On the Syam sheets each question column is a tall pink rectangle
    (the shaded band that holds 40 rows x 4 circles). They are the
    largest red-form contours in the lower half: tall (over 35% of
    the page height) and narrow (8-18% of the page width). A block
    wider than one column (the 150Q sheet joins three columns into
    one pink block) is split at its white gaps instead of dropped.
    A short wide block also counts as a column: the 20Q daily-test
    strip has 4 columns of 5 rows each, each about 17% of the page
    wide and 37% of the page tall — wide, not tall — so a rectangle
    at least 20% of the page tall and 8% of the page wide is a
    column too, even when it is wider than it is tall.
    Returns (x1, y1, x2, y2) sorted left to right.
    """
    h, w = image_bgr.shape[:2]
    mask = redness_mask(image_bgr)
    mask[:search_y1, :] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    cols = []
    wide = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bh < h * 0.20 or bw < w * 0.05:
            continue
        if bw > w * 0.25:
            # Possibly several answer columns joined into one pink
            # block (150Q sheet): split it below instead of dropping
            # it, or the sheet yields no bubbles at all.
            wide.append((x, y, x + bw, y + bh))
            continue
        if bh >= h * 0.35 and bh >= bw * 3:
            # Tall narrow column (40-row sheets).
            cols.append((x, y, x + bw, y + bh))
        elif bh >= 60 and bw >= w * 0.08:
            # Short wide column (20Q strip: 5 rows, wider than tall).
            cols.append((x, y, x + bw, y + bh))
    cols.sort(key=lambda c: c[0])
    # Merge overlapping detections of the same column.
    merged = []
    for c in cols:
        if merged and c[0] < merged[-1][2] - 10 and abs(c[1] - merged[-1][1]) < 20:
            m = merged[-1]
            merged[-1] = (min(m[0], c[0]), min(m[1], c[1]),
                          max(m[2], c[2]), max(m[3], c[3]))
            continue
        merged.append(c)
    for rect in wide:
        for piece in _split_wide_block(mask, rect, w):
            pw, ph = piece[2] - piece[0], piece[3] - piece[1]
            if w * 0.05 <= pw <= w * 0.25 and (
                    (ph >= h * 0.35 and ph >= 3 * pw)
                    or (ph >= h * 0.20 and ph >= 60 and pw >= w * 0.08)):
                merged.append(piece)
    merged.sort(key=lambda c: c[0])
    return merged


def _candidate_centres(image_bgr: np.ndarray,
                       col: Tuple[int, int, int, int]) -> List[Tuple[float, float]]:
    """Candidate bubble centres inside one answer column.

    Hough circles on the grey image find both empty outlines and
    dark filled bubbles; dark-blob contours add filled bubbles whose
    outline is obscured. Both are noisy alone — the grid fit below
    keeps only candidates that line up in 4 even columns.
    """
    x1, y1, x2, y2 = col
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    roi = gray[y1:y2, x1:x2]
    if roi.size == 0:
        return []
    scale = image_bgr.shape[1] / 1644.0
    pts: List[Tuple[float, float]] = []
    try:
        circles = cv2.HoughCircles(
            cv2.medianBlur(roi, 5), cv2.HOUGH_GRADIENT, 1, 16,
            param1=100, param2=16,
            minRadius=int(max(5, 7 * scale)), maxRadius=int(max(9, 18 * scale)))
        if circles is not None:
            for cx, cy, _r in circles[0]:
                pts.append((float(cx + x1), float(cy + y1)))
    except Exception:
        pass
    # Dark filled blobs.
    _, dark = cv2.threshold(roi, 100, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 60 * scale * scale or area > 2500 * scale * scale:
            continue
        (cx, cy), r = cv2.minEnclosingCircle(cnt)
        if r < 6 * scale or r > 19 * scale:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw <= 0 or bh <= 0 or abs(bw - bh) / max(bw, bh) > 0.5:
            continue
        pts.append((float(cx + x1), float(cy + y1)))
    return pts


def _histogram_peaks(values: List[float], bin_w: float,
                     min_gap: float, count: int) -> List[float]:
    """Top `count` histogram peaks in `values`, at least min_gap apart."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    nbins = max(1, int((hi - lo) / bin_w) + 1)
    hist = [0] * nbins
    for v in values:
        hist[min(nbins - 1, int((v - lo) / bin_w))] += 1
    order = sorted(range(nbins), key=lambda i: hist[i], reverse=True)
    peaks = []
    for i in order:
        centre = lo + (i + 0.5) * bin_w
        if hist[i] == 0:
            break
        if any(abs(centre - p) < min_gap for p in peaks):
            continue
        peaks.append(centre)
        if len(peaks) >= count:
            break
    return sorted(peaks)


def _row_centres_from_candidates(cands: List[Tuple[float, float]],
                                 rows_per_col: int,
                                 grid_ys: List[float],
                                 tol: float = 10.0
                                 ) -> List[float]:
    """Row y-centres from the real detected circles (centre sampling).

    Clusters the candidate circle y's into rows, in top-to-bottom
    order, and returns one y per row. The grid y's are only a
    reference: they decide which clusters to drop when there are too
    many, and fill rows that have no cluster. A cluster is never
    assigned to a row more than half a pitch from its grid line, so
    a sample can never jump to the neighbour row's bubble — the
    neighbour is a full pitch away.

    Why this exists: on the 200Q Syam sheet the fixed template's
    rows sit ~25 px (almost one full row) below the real bubbles at
    the top of each column — its base y (1151) does not match the
    sheet (first real row ~1123.5) — so the fixed reader samples the
    next row's marks and scores 7 lucky corrects. The dynamic grid
    has the same weakness in principle: its pitch comes from the
    pink rectangle's height, which runs past the last bubble row.
    Clusters in order cannot make that mistake: the first cluster
    is the first row, because no row can hide above it inside the
    column rectangle.
    """
    ys = sorted(c[1] for c in cands)
    groups: List[List[float]] = []
    for y in ys:
        if groups and y - groups[-1][-1] <= tol:
            groups[-1].append(y)
        else:
            groups.append([y])
    # (median y, candidate count) per cluster, in order.
    cl = [(float(np.median(g)), len(g)) for g in groups]
    n = rows_per_col
    if not cl:
        return list(grid_ys)
    if len(cl) == n:
        return [c[0] for c in cl]
    pitch = ((grid_ys[-1] - grid_ys[0]) / (n - 1)
             if n > 1 else 30.0)
    if len(cl) > n:
        # Too many clusters (a smudge, a stray mark): keep the n
        # strongest ones — a real row has ~4-5 candidates — closest
        # to the grid, then take them in order.
        def _score(c):
            return (c[1], -min(abs(c[0] - g) for g in grid_ys))
        keep = sorted(sorted(cl, key=_score, reverse=True)[:n],
                      key=lambda c: c[0])
        return [c[0] for c in keep]
    # Too few clusters: fit the row grid to the clusters themselves.
    # The grid pitch comes from the pink rectangle, which runs past
    # the last bubble row, so the grid can sit half a pitch off the
    # real rows (150Q sheet: grid row 0 at 657, first real row at
    # 674). Snapping each cluster to its nearest grid line then
    # leaves a spurious grid value in a gap between two real rows
    # and shifts every row below it by one (150Q sheet 388765: grid
    # row 1 kept 690, a gap, so Q2 read the gap and Q3 read Q2's
    # row). Instead, the pitch is the median gap between consecutive
    # clusters and the first cluster is the first row (no row can
    # hide above it inside the column rectangle). Each cluster lands
    # on the fitted row nearest to it, and rows with no cluster take
    # the fitted value — never a stale grid value in a gap.
    if len(cl) >= 2:
        diffs = [cl[i + 1][0] - cl[i][0] for i in range(len(cl) - 1)]
        fit_pitch = float(np.median(diffs))
        if fit_pitch <= 0:
            fit_pitch = pitch
    else:
        fit_pitch = pitch
    fit_ys = [cl[0][0] + i * fit_pitch for i in range(n)]
    out = list(fit_ys)
    for (cy, _cnt) in cl:
        best, best_d = None, fit_pitch / 2.0
        for i in range(n):
            d = abs(cy - fit_ys[i])
            if d <= best_d:
                best, best_d = i, d
        if best is not None:
            out[best] = cy
    return out


def _grid_rows_from_columns(image_bgr: np.ndarray,
                           columns: List[Tuple[int, int, int, int]],
                           expected_questions: Optional[int]
                           ) -> List[Tuple[float, float, float, float]]:
    """Bubble centres from the detected answer columns.

    Returns a list of (cx, cy, radius, column_x) — one per bubble —
    on a regular grid derived from the sheet itself:
      * number of columns = number of pink column rectangles found
      * rows per column = expected_questions / columns (from the key
        PDF count; falls back to 40 when no count is given) — the
        last column holds the remainder when the count does not
        divide evenly (50 questions over 4 columns is 13, 13, 13,
        11, not 12 each; see _rows_per_column)
      * row pitch = column height / rows per column
      * the 4 circle x-positions per column come from peaks in the
        candidate-centre x histogram inside that column; when too
        few candidates are found they fall back to even spacing
        across the column width.
      * each row's y comes from the real detected circles, clustered
        in order (see _row_centres_from_candidates): the pitch from
        the column rectangle is slightly too large (the pink band
        runs past the last bubble row), so a plain grid drifts a
        full row by the bottom of a column, and snapping to the
        median near a drifted grid line can lock onto the neighbour
        row's circles. Clusters in order cannot jump a row.
    """
    h, w = image_bgr.shape[:2]
    scale = w / 1644.0
    if not columns:
        return []
    n_cols = len(columns)
    rows_list = _rows_per_column(expected_questions, n_cols)
    out: List[Tuple[float, float, float, float]] = []
    for (x1, y1, x2, y2), rows_per_col in zip(columns, rows_list):
        col_w, col_h = float(x2 - x1), float(y2 - y1)
        pitch_y = col_h / float(rows_per_col)
        cands = _candidate_centres(image_bgr, (x1, y1, x2, y2))
        xs = [c[0] for c in cands if x1 <= c[0] <= x2]
        peaks = _histogram_peaks(xs, bin_w=5.0 * scale,
                                 min_gap=18.0 * scale, count=4)
        if len(peaks) == 4:
            centres_x = peaks
        else:
            # Even spacing across the column, leaving room on the
            # left for the printed question number.
            centres_x = [x1 + col_w * (0.32 + 0.17 * k) for k in range(4)]
        # Row y: centre sampling. The row centres come from the real
        # detected circles (clustered in order), not from the pink
        # rectangle's height: the rectangle is slightly taller than
        # the bubble block, so its pitch is too large and a plain
        # grid drifts a full row by the bottom of a column — and the
        # old per-row median snap could then lock onto the neighbour
        # row's circles. Clusters in order cannot jump a row; rows
        # with no cluster keep the grid value.
        grid_ys = [y1 + pitch_y * (i + 0.5) for i in range(rows_per_col)]
        row_ys = _row_centres_from_candidates(cands, rows_per_col,
                                              grid_ys)
        radius = float(np.clip(col_w * 0.065, 7 * scale, 14 * scale))
        for i in range(rows_per_col):
            cy = row_ys[i]
            for cx in centres_x:
                out.append((float(cx), float(cy), radius, float(x1)))
    return out


def _find_circles(image_bgr: np.ndarray,
                  search_y1: int) -> List[Tuple[float, float, float]]:
    """Backwards-compatible helper: circles via the column grid.

    Kept for callers/tests that expect (cx, cy, r) triples. The
    full dynamic pass uses _grid_rows_from_columns directly, with
    the expected question count from the key PDF.
    """
    cols = _find_answer_columns(image_bgr, search_y1)
    grid = _grid_rows_from_columns(image_bgr, cols, expected_questions=None)
    return [(cx, cy, r) for (cx, cy, r, _x) in grid]


def _group_circles_into_rows(circles: List[Tuple[float, float, float]],
                             image_w: int) -> List[List[Tuple[float, float, float]]]:
    """Group circles into rows of (ideally) 4, on the same horizontal line."""
    if not circles:
        return []
    r_med = _median([c[2] for c in circles], default=10.0)
    tol_y = max(r_med * 1.2, 6.0)
    rows: List[List[Tuple[float, float, float]]] = []
    for c in sorted(circles, key=lambda c: (c[1], c[0])):
        placed = False
        for row in rows:
            y_med = _median([r[1] for r in row])
            if abs(c[1] - y_med) <= tol_y:
                row.append(c)
                placed = True
                break
        if not placed:
            rows.append([c])
    out = []
    for row in rows:
        row.sort(key=lambda c: c[0])
        # Keep only rows of exactly 4 circles with even spacing;
        # a row of 3 or 5 is a detection error, not a question.
        if len(row) == 4:
            xs = [c[0] for c in row]
            gaps = [xs[i + 1] - xs[i] for i in range(3)]
            if gaps and max(gaps) < 3.5 * min(gaps) and min(gaps) > r_med * 0.8:
                out.append(row)
    out.sort(key=lambda row: (_median([c[1] for c in row]),
                              _median([c[0] for c in row])))
    return out


def _answers_start_y(image_bgr: np.ndarray, ocr_engine=None,
                     labels: Optional[List[Dict]] = None) -> int:
    """Y below which answer bubbles live: under the ANSWERS heading.

    Falls back to the top third of the page when the heading text
    cannot be read — the identity / booklet area is above that.

    `labels`, when given, is the full-page OCR result already
    computed by the caller — it is reused instead of running the
    slow full-page OCR a second time for the same image.
    """
    h, _w = image_bgr.shape[:2]
    if labels is None:
        labels = find_labels(image_bgr, ocr_engine=ocr_engine)
    for lab in labels:
        if "answer" in lab["norm"]:
            return int(lab["y2"]) + 5
    return int(h * 0.33)


@dataclass
class DynamicSheet:
    identity: DynamicIdentity = field(default_factory=DynamicIdentity)
    rows: Dict[int, DynamicBubbleRow] = field(default_factory=dict)
    expected_questions: Optional[int] = None
    found_questions: int = 0
    method: str = ""            # "dynamic" | "dynamic-partial" | "none"
    warnings: List[str] = field(default_factory=list)


def analyze_sheet_dynamic(image_bgr: np.ndarray,
                          expected_questions: Optional[int] = None,
                          ocr_engine=None,
                          exam_prefix: Optional[str] = None) -> DynamicSheet:
    """Full dynamic pass over one (already straightened) sheet image.

    1. Identity from label-anchored box rows.
    2. Bubbles from question-number rows below ANSWERS.
    3. Question numbers are assigned column-major (down each
       column, then the next column to the right) — the standard
       OMR order on the Syam sheets — and checked against the
       key-PDF count when one is given.
    exam_prefix, when known (roster / batch / user-supplied), is
    used only to fix look-alike misreads in the hall ticket.
    """
    warnings: List[str] = []
    # The full-page OCR is the slowest step (several seconds), so
    # run it ONCE for this sheet and share the labels between the
    # identity reader and the ANSWERS-heading search below. Reading
    # the same page twice was the single biggest cost per sheet.
    labels = find_labels(image_bgr, ocr_engine=ocr_engine)
    identity = extract_identity_dynamic(image_bgr, ocr_engine=ocr_engine,
                                        exam_prefix=exam_prefix,
                                        labels=labels)

    start_y = _answers_start_y(image_bgr, ocr_engine=ocr_engine,
                               labels=labels)
    columns = _find_answer_columns(image_bgr, search_y1=start_y)
    if not columns:
        warnings.append("No answer columns found below ANSWERS.")
        return DynamicSheet(identity=identity, expected_questions=expected_questions,
                            method="none", warnings=warnings)
    grid = _grid_rows_from_columns(image_bgr, columns, expected_questions)
    if not grid:
        warnings.append("No bubble grid found in the answer columns.")
        return DynamicSheet(identity=identity, expected_questions=expected_questions,
                            method="none", warnings=warnings)

    # Group the flat grid list back into rows: 4 bubbles per row,
    # rows in column-major order (down each column, then next column).
    ink = ink_map(image_bgr)
    h_img, w_img = ink.shape
    result_rows: Dict[int, DynamicBubbleRow] = {}
    q = 1
    # grid is already column-major (columns left->right, rows top->bottom)
    for i in range(0, len(grid) - 3, 4):
        chunk = grid[i:i + 4]
        if len(chunk) < 4:
            break
        centres = [(c[0], c[1]) for c in chunk]
        radii = [c[2] for c in chunk]
        r = _median(radii, default=float(BUBBLE_RADIUS))
        core_r = int(max(2, r * 0.75))
        fills: List[float] = []
        for (cx, cy) in centres:
            ix, iy = int(round(cx)), int(round(cy))
            x1, x2 = max(0, ix - core_r), min(w_img, ix + core_r + 1)
            y1, y2 = max(0, iy - core_r), min(h_img, iy + core_r + 1)
            patch = ink[y1:y2, x1:x2]
            fills.append(float(np.mean(patch)) if patch.size else 0.0)
        opt, status, conf = _classify_fills(fills)
        result_rows[q] = DynamicBubbleRow(
            question_number=q, centres=centres, fills=[round(f, 2) for f in fills],
            detected_option=opt, status=status, confidence=round(conf, 3))
        q += 1

    found = len(result_rows)
    method = "dynamic"
    if expected_questions:
        if found != expected_questions:
            warnings.append(
                f"Found {found} bubble rows but key PDF has "
                f"{expected_questions} questions.")
            if found < expected_questions * 0.8:
                method = "dynamic-partial"
        if found == 0:
            method = "none"
    return DynamicSheet(identity=identity, rows=result_rows,
                        expected_questions=expected_questions,
                        found_questions=found, method=method,
                        warnings=warnings)


def dynamic_rows_to_detected(sheet: DynamicSheet) -> Dict[int, Dict]:
    """Convert dynamic bubble rows to the result format
    ScoringEngine expects, so it can score them unchanged."""
    out: Dict[int, Dict] = {}
    for q, row in sheet.rows.items():
        fills = row.fills
        best = max(fills) if fills else 0.0
        second = sorted(fills, reverse=True)[1] if len(fills) > 1 else 0.0
        ratio = best / (second + 1e-4) if second else 99.0
        out[q] = {
            "detected_option": row.detected_option,
            "status": row.status,
            "confidence": row.confidence,
            "fills": fills,
            "max_fill": round(best, 2),
            "ratio": round(ratio, 2),
        }
    return out
