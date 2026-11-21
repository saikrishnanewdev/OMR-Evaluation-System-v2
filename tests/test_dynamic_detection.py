"""Tests for dynamic OMR extraction (app/omr/dynamic.py).

No layout, no fixed coordinates: hall ticket / name come from the
label-anchored box rows, bubbles come from the answer columns found
on the sheet itself, and the key-PDF count only sets how many
questions to expect. These tests need only OpenCV + NumPy (+ PyMuPDF
via the preprocessor) — no RapidOCR, no GUI, no database.
"""
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.omr.dynamic import (
    analyze_sheet_dynamic,
    dynamic_rows_to_detected,
    find_box_rows,
)

REPO = Path(__file__).resolve().parent.parent
SAMPLE_160 = REPO / "OMR_325601.jpg"
TEMPLATE_200 = REPO / "OMR_200_Sheet_Template.png"

PINK = (120, 80, 230)  # BGR: red channel clearly above green/blue


def _synthetic_top_image():
    """White sheet with pink box rows at arbitrary (non-fixed) y.

    Hall ticket row: 16 boxes at y=300. Name row: 22 boxes at y=360.
    Gender row: 5 boxes at y=420 — must not be mistaken for a name.
    """
    img = np.full((1200, 1644, 3), 255, dtype=np.uint8)
    for y, n in ((300, 16), (360, 22), (420, 5)):
        box = 34
        x0 = 450
        for i in range(n):
            x = x0 + i * box
            cv2.rectangle(img, (x, y), (x + box, y + box), PINK, 2)
    return img


def test_find_box_rows_on_synthetic_sheet():
    img = _synthetic_top_image()
    rows = find_box_rows(img)
    assert len(rows) >= 3
    # First two long rows are hall ticket (16) then name (22).
    assert rows[0].num_boxes == 16
    assert rows[1].num_boxes == 22
    assert rows[0].y < rows[1].y
    assert rows[0].boxes[0][0] < rows[0].boxes[-1][0]


def test_dynamic_identity_rows_on_200q_template():
    img = cv2.imread(str(TEMPLATE_200))
    assert img is not None
    rows = find_box_rows(img)
    assert len(rows) >= 2
    # Hall ticket is the first long row, name the second.
    assert rows[0].num_boxes >= 12
    assert rows[1].num_boxes >= 18
    assert rows[0].y < rows[1].y


def test_dynamic_blank_200q_template_finds_200_blank():
    img = cv2.imread(str(TEMPLATE_200))
    assert img is not None
    result = analyze_sheet_dynamic(img, expected_questions=200, ocr_engine=None)
    assert result.method == "dynamic"
    assert result.found_questions == 200
    assert all(r.detected_option == "BLANK" for r in result.rows.values())


def test_key_count_drives_question_count():
    """Same 200Q sheet, key says 160: dynamic must return 160 rows,
    not the hardcoded 200 — the key PDF sets the count."""
    img = cv2.imread(str(TEMPLATE_200))
    assert img is not None
    result = analyze_sheet_dynamic(img, expected_questions=160, ocr_engine=None)
    assert result.found_questions == 160


def test_dynamic_agrees_with_fixed_on_160q_sample():
    """Real filled 160Q sheet: dynamic must match the fixed template
    detector almost exactly (the fixed one is the proven baseline)."""
    from app.omr.bubble_detector import BubbleDetector
    from app.omr.preprocessor import Preprocessor
    from app.omr.template import get_template

    img = cv2.imread(str(SAMPLE_160))
    assert img is not None
    aligned, _skew = Preprocessor.align_and_deskew(img)
    ink = Preprocessor.extract_ink_channel(aligned)
    left_m, right_m, _ = Preprocessor.detect_timing_tracks(img)
    fixed = BubbleDetector(get_template(160)).analyze_sheet(
        ink, timing_marks=(left_m, right_m))
    dyn = analyze_sheet_dynamic(aligned, expected_questions=160, ocr_engine=None)
    assert dyn.method == "dynamic"
    assert dyn.found_questions == 160
    detected = dynamic_rows_to_detected(dyn)
    agree = sum(1 for q in fixed
                if fixed[q]["detected_option"] == detected[q]["detected_option"])
    assert agree >= 152, f"dynamic/fixed agree only {agree}/160"


def test_dynamic_on_blank_image_returns_none():
    img = np.full((1200, 1600, 3), 255, dtype=np.uint8)
    result = analyze_sheet_dynamic(img, expected_questions=20, ocr_engine=None)
    assert result.method == "none"
    assert result.found_questions == 0
    assert result.rows == {}
