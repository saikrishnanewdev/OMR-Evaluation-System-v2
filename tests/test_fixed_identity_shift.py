"""Unit tests for the fixed-reader row following (_identity_rows).

The fixed identity reader cuts the HT/name strips from hardcoded x
(200Q: 515, 160Q: 440), but after the warp the rows can sit left or
right of that (observed 200Q HT starts: 521, 478, 437). The helper
finds the HT and name box rows on the sheet so the reader can cut its
strips from the rows themselves. No OCR is needed here: the helper
only looks at the printed red box outlines.
"""

import cv2
import numpy as np

from app.ocr.engine import _identity_rows

PINK = (120, 80, 230)  # BGR: red channel clearly above green/blue
W, H = 1644, 2272


def _box_row(img, x1, y1, n_boxes, box_w=41, box_h=46):
    """Draw one row of adjacent pink-outlined character boxes."""
    for i in range(n_boxes):
        x = x1 + i * box_w
        cv2.rectangle(img, (x, y1), (x + box_w, y1 + box_h), PINK, 2)


def _sheet(ht_x1=438, ht_y1=189, n_ht=18, name_x1=438, name_y1=241,
           n_name=24, fragment=True):
    """Synthetic aligned sheet: HT row + name row, both starting at ht_x1,
    plus (by default) the 11-box fragment row above the HT row that real
    sheets show at y~168 — it must be ignored (outside the HT y-band).

    NOTE: cv2.rectangle with thickness 2 draws 1px outside the given
    coordinates, so the finder sees a row starting at ht_x1 - 1. The
    default ht_x1=438 therefore reads as a row at x=437 (like
    OMR_388772/388773).
    """
    img = np.full((H, W, 3), 255, dtype=np.uint8)
    if fragment:
        _box_row(img, 585, 157, 11, box_w=16, box_h=22)
    _box_row(img, ht_x1, ht_y1, n_ht)
    _box_row(img, name_x1, name_y1, n_name)
    return img


def test_rows_found_left_shifted():
    # Rows start at x=437 like OMR_388772/388773; the 18-box HT row is
    # picked, not the 11-box fragment above it.
    ht_row, name_row = _identity_rows(_sheet(), True)
    assert ht_row is not None and name_row is not None
    assert ht_row.x1 == 437 and ht_row.num_boxes == 18
    assert ht_row.y == 212
    assert name_row.x1 == 437 and name_row.num_boxes == 24
    assert name_row.y == 264


def test_rows_found_aligned():
    # Rows already where the template expects them.
    ht_row, name_row = _identity_rows(
        _sheet(ht_x1=516, name_x1=516), True)
    assert ht_row is not None and name_row is not None
    assert ht_row.x1 == 515 and name_row.x1 == 515


def test_rows_found_right_shifted():
    # Rows start right of the template x (like OMR_348819 at 521).
    ht_row, name_row = _identity_rows(
        _sheet(ht_x1=522, name_x1=522), True)
    assert ht_row is not None and name_row is not None
    assert ht_row.x1 == 521 and name_row.x1 == 521


def test_rows_none_when_blank():
    ht_row, name_row = _identity_rows(
        np.full((H, W, 3), 255, dtype=np.uint8), True)
    assert ht_row is None and name_row is None


def test_rows_none_when_outside_band():
    # A box row far below the HT/name bands must not be picked up.
    img = np.full((H, W, 3), 255, dtype=np.uint8)
    _box_row(img, 300, 600, 18)
    ht_row, name_row = _identity_rows(img, True)
    assert ht_row is None and name_row is None


def test_rows_160q():
    # 160Q bands: HT y 208-266, name y 254-314; template x is 440.
    img = _sheet(ht_x1=401, ht_y1=214, name_x1=401, name_y1=261,
                 fragment=False)
    ht_row, name_row = _identity_rows(img, False)
    assert ht_row is not None and name_row is not None
    assert ht_row.x1 == 400 and name_row.x1 == 400
