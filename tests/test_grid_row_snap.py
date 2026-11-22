"""Grid row snapping: bubble-row y must follow the real bubbles, not
the column rectangle.

On real sheets the pink answer column runs a little past the last
bubble row, so pitch = column height / 40 is slightly too large and
the grid drifts ~10 px low by the last row (Q120/Q200 read blank,
Q78 read AMBIGUOUS). _grid_rows_from_columns must snap each row to
the median candidate y near its grid line.

Synthetic sheet: one pink column 1000 px tall holding 40 rows at a
true pitch of 25 px, inside a 1020 px column rectangle (grid pitch
25.5 px) — the last grid row is ~20 px below the real bubbles.
"""

import cv2
import numpy as np

from app.omr.dynamic import _grid_rows_from_columns


def _synthetic_sheet():
    img = np.full((1400, 1000, 3), 255, dtype=np.uint8)
    # Pink answer column (BGR: high red, lower green/blue).
    cv2.rectangle(img, (100, 100), (280, 1120), (180, 180, 255), -1)
    # 40 rows x 4 circles, true pitch 25, first centre y = 112.5.
    for i in range(40):
        cy = int(round(100 + 25 * (i + 0.5)))
        for k in range(4):
            cx = 140 + k * 40
            cv2.circle(img, (cx, cy), 10, (0, 0, 200), 2)
        # Fill one bubble per row (dark), like a real answered sheet.
        cv2.circle(img, (140 + (i % 4) * 40, cy), 9, (30, 30, 30), -1)
    return img


def test_last_row_snaps_to_real_bubbles():
    img = _synthetic_sheet()
    grid = _grid_rows_from_columns(img, [(100, 100, 280, 1120)], 40)
    assert len(grid) == 40 * 4
    # Row 0: grid and true centres nearly agree.
    first_cy = np.median([c[1] for c in grid[0:4]])
    assert abs(first_cy - 112.5) <= 3.0, f"row 0 cy {first_cy}"
    # Row 39 (last): the raw grid would sit ~20 px too low.
    last_cy = np.median([c[1] for c in grid[-4:]])
    assert abs(last_cy - 1087.5) <= 3.0, f"row 39 cy {last_cy}"


def test_middle_row_snaps_to_real_bubbles():
    img = _synthetic_sheet()
    grid = _grid_rows_from_columns(img, [(100, 100, 280, 1120)], 40)
    mid_cy = np.median([c[1] for c in grid[20 * 4:20 * 4 + 4]])
    assert abs(mid_cy - (100 + 25 * 20.5)) <= 3.0, f"row 20 cy {mid_cy}"
