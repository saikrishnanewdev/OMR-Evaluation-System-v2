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

from app.evaluation.answer_key import AnswerKeyExtractor
from app.evaluation.scoring_engine import ScoringEngine
from app.omr.dynamic import (
    analyze_sheet_dynamic,
    dynamic_rows_to_detected,
    find_box_rows,
)

REPO = Path(__file__).resolve().parent.parent
SAMPLE_160 = REPO / "OMR_325601.jpg"
SAMPLE_KEY = REPO / "SA-08.pdf"

PINK = (120, 80, 230)  # BGR: red channel clearly above green/blue
LIGHT_PINK = (210, 200, 245)  # BGR: light pink column fill (real sheets)


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


def _synthetic_blank_sheet():
    """White 1644x2272 sheet with 5 light-pink answer columns, each
    holding 40 rows x 4 empty circles — a blank 200-question sheet
    with no fixed layout anywhere."""
    img = np.full((2272, 1644, 3), 255, dtype=np.uint8)
    for (x1, x2) in [(200, 380), (500, 680), (800, 980),
                     (1100, 1280), (1400, 1580)]:
        img[650:2250, x1:x2] = LIGHT_PINK
        for r in range(40):
            cy = 700 + r * 38
            for k in range(4):
                cx = x1 + 25 + k * 40
                cv2.circle(img, (cx, cy), 11, (60, 60, 60), 2)
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


def test_box_rows_found_at_arbitrary_position():
    """The same box rows moved to a different y must still be found
    in order — nothing about their position is hardcoded."""
    img = np.full((1200, 1644, 3), 255, dtype=np.uint8)
    # Both rows inside the top 45% of the sheet, where the box-row
    # finder looks (identity rows live at the top of the page).
    for y, n in ((300, 18), (450, 24)):
        box = 34
        x0 = 300
        for i in range(n):
            x = x0 + i * box
            cv2.rectangle(img, (x, y), (x + box, y + box), PINK, 2)
    rows = find_box_rows(img)
    assert len(rows) >= 2
    assert rows[0].num_boxes == 18
    assert rows[1].num_boxes == 24
    assert rows[0].y < rows[1].y


def test_dynamic_blank_sheet_finds_200_blank():
    img = _synthetic_blank_sheet()
    result = analyze_sheet_dynamic(img, expected_questions=200, ocr_engine=None)
    assert result.method == "dynamic"
    assert result.found_questions == 200
    assert all(r.detected_option == "BLANK" for r in result.rows.values())


def test_key_count_drives_question_count():
    """Same blank sheet, key says 160: dynamic must return 160 rows,
    not the hardcoded 200 — the key PDF sets the count."""
    img = _synthetic_blank_sheet()
    result = analyze_sheet_dynamic(img, expected_questions=160, ocr_engine=None)
    assert result.found_questions == 160


def test_dynamic_160q_sample_scores_107():
    """Real filled 160Q sheet: dynamic reads 107 correct / 53 wrong
    / 0 unattempted against the SA-08 key (the documented benchmark)."""
    from app.omr.preprocessor import Preprocessor

    img = cv2.imread(str(SAMPLE_160))
    assert img is not None
    aligned, _skew = Preprocessor.align_and_deskew(img)
    dyn = analyze_sheet_dynamic(aligned, expected_questions=160, ocr_engine=None)
    assert dyn.method == "dynamic"
    assert dyn.found_questions == 160
    key = AnswerKeyExtractor().extract_from_pdf(SAMPLE_KEY)
    assert len(key.items) == 160
    scorer = ScoringEngine(correct_mark=0.50, wrong_mark=0.00,
                           unattempted_mark=0.00, total_questions=160)
    _, correct, wrong, unattempted, marks, _, _ = scorer.evaluate_sheet(
        dynamic_rows_to_detected(dyn), key.items)
    assert (correct, wrong, unattempted) == (107, 53, 0)
    assert marks == 53.50


def test_dynamic_on_blank_image_returns_none():
    img = np.full((1200, 1600, 3), 255, dtype=np.uint8)
    result = analyze_sheet_dynamic(img, expected_questions=20, ocr_engine=None)
    assert result.method == "none"
    assert result.found_questions == 0
    assert result.rows == {}
