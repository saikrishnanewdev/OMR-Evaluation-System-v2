"""Identity accuracy: trim to filled boxes + hall-ticket look-alike
correction.

Background (200Q Syam sheet, img0077): the recogniser was fed the
whole box row, so the empty boxes after the text fed it faint edges
that it invented letters from ('APOSC1ZGG', 'RA M A RAOTDODLD').
Reading only the filled boxes gives 'Ap05c1799' / 'ramarao'; the
prefix anchoring then fixes the last look-alike (J read as 1).
"""

import numpy as np

from app.omr.dynamic import (
    BoxRow,
    _filled_box_span,
    correct_hall_ticket,
)


def _row_image(n_boxes, filled, box_w=28, box_h=39):
    """White image with one box row; filled boxes hold a dark blob."""
    img = np.full((200, 1000, 3), 255, dtype=np.uint8)
    boxes = []
    for i in range(n_boxes):
        x = 100 + i * box_w
        y = 50
        boxes.append((x, y, box_w, box_h))
        # Red box outline (the printed form).
        import cv2
        cv2.rectangle(img, (x, y), (x + box_w, y + box_h),
                      (180, 180, 255), 1)
        if i in filled:
            cv2.rectangle(img, (x + 8, y + 8), (x + box_w - 8, y + box_h - 8),
                          (30, 30, 30), -1)
    row = BoxRow(y=69, y1=50, y2=89, x1=100,
                 x2=100 + n_boxes * box_w,
                 box_w=float(box_w), box_h=float(box_h),
                 num_boxes=n_boxes, boxes=boxes)
    return img, row


def test_filled_span_finds_filled_run():
    img, row = _row_image(10, {0, 1, 2, 3, 4, 5, 6})
    assert _filled_box_span(img, row) == (0, 6)


def test_filled_span_ignores_leading_empty_boxes():
    img, row = _row_image(10, {2, 3, 4})
    assert _filled_box_span(img, row) == (2, 4)


def test_filled_span_blank_row_returns_none():
    img, row = _row_image(10, set())
    assert _filled_box_span(img, row) is None


def test_filled_span_row_without_boxes_returns_none():
    img, _ = _row_image(10, {0, 1})
    row = BoxRow(y=69, y1=50, y2=89, x1=100, x2=380,
                 box_w=28.0, box_h=39.0, num_boxes=10, boxes=[])
    assert _filled_box_span(img, row) is None


def test_correct_hall_ticket_prefix_fixes_j():
    # The headline case: trimmed OCR fuses handwritten J + 1 into a
    # single '1' (9 chars for 10 filled boxes); the batch prefix
    # says position 6 is a letter, J, and the fused digit is the
    # first roll digit, so it is restored at the start of the roll.
    assert correct_hall_ticket("AP05C1799", "AP05CJ",
                               expected_len=10) == "AP05CJ1799"


def test_correct_hall_ticket_prefix_fixes_zero_and_five():
    assert correct_hall_ticket("APOSC1799", "AP05CJ",
                               expected_len=10) == "AP05CJ1799"


def test_correct_hall_ticket_without_box_count_keeps_shortfall():
    # Without the filled-box count there is no way to know a
    # character was fused, so only the prefix letters are fixed.
    assert correct_hall_ticket("AP05C1799", "AP05CJ") == "AP05CJ799"


def test_correct_hall_ticket_no_prefix_trailing_letter():
    assert correct_hall_ticket("APOSC179O", None) == "APOSC1790"
    assert correct_hall_ticket("AP05C1799", None) == "AP05C1799"
    assert correct_hall_ticket("", None) == ""


def test_correct_hall_ticket_mismatched_prefix_ignored():
    # A roster/batch prefix from another exam must never corrupt
    # the reading.
    assert correct_hall_ticket("AP05C1799", "KKD2025KTS") == "AP05C1799"
    assert correct_hall_ticket("KNLL02R5ATS0000", "KNL2025SATS") == \
        "KNLL02R5ATS0000"
