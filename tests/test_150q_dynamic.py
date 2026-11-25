"""Tests for the 150Q sheet support (OMR_388765 / OMR_388766).

The 150Q sheet differs from the 200Q sheet in three ways the dynamic
reader assumed away:
  * its three answer columns sit in ONE joined pink block, not three
    separate rectangles;
  * its name row is joined to the gender/community rows below by a
    vertical red line, so the row finder sees one tall contour;
  * RapidOCR returns its labels as one word ('HALLTICKETNUMBER'),
    so the label match (which looked for 'hall ticket') failed.
A fourth, latent problem showed up while verifying the bubbles: when
a column yields one cluster fewer than the row count, the old
nearest-grid assignment left a stale grid value in a gap and shifted
every row below it by one (388765: grid row 1 kept 690, so Q2 read
the gap and Q3 read Q2's row).
"""
import numpy as np
import pytest

from app.omr.dynamic import (
    BoxRow,
    _find_answer_columns,
    _row_centres_from_candidates,
    _row_for_label,
    find_box_rows,
)

PINK = (200, 190, 235)  # BGR: R clearly above G and B (redness mask)
RED = (60, 60, 220)
WHITE = (255, 255, 255)


def _pink_block_with_gaps():
    """1644x2272 white sheet, one pink block (3 columns) with white
    gaps between the columns, joined by a pink bar across the top so
    it is a single contour — the 150Q layout."""
    img = np.full((2272, 1644, 3), WHITE, dtype=np.uint8)
    # Three pink columns with white gaps, plus a top bar joining them.
    for (x1, x2) in [(941, 1150), (1178, 1350), (1378, 1539)]:
        img[660:2272, x1:x2] = PINK
    img[641:660, 941:1539] = PINK
    return img


def test_wide_block_splits_into_three_columns():
    img = _pink_block_with_gaps()
    cols = _find_answer_columns(img, search_y1=245)
    assert len(cols) == 3
    # Split points land inside the white gaps (1150-1178, 1350-1378),
    # not necessarily at the exact column edges.
    assert cols[0][0] == 941 and 1150 <= cols[0][2] <= 1178
    assert cols[1][0] == cols[0][2] and 1350 <= cols[1][2] <= 1378
    assert cols[2][0] == cols[1][2] and cols[2][2] == 1539
    for (x1, y1, x2, y2) in cols:
        assert y1 == 641 and y2 == 2272


def test_wide_block_without_gaps_is_dropped():
    """A solid wide block (no white gaps) cannot be split, so it is
    dropped exactly as before — no phantom columns."""
    img = np.full((2272, 1644, 3), WHITE, dtype=np.uint8)
    img[641:2272, 941:1539] = PINK
    assert _find_answer_columns(img, search_y1=245) == []


def _box_row_image():
    """Top area: HT row (18 boxes, separate), then name (22), gender
    (5) and community (7) rows joined by a vertical red line down
    their left edge — the 150Q identity area."""
    import cv2
    img = np.full((2272, 1644, 3), WHITE, dtype=np.uint8)
    def row(y1, x1, n, bw=41):
        for i in range(n):
            x = x1 + i * bw
            cv2.rectangle(img, (x, y1), (x + bw, y1 + 40), RED, 2)
    row(100, 440, 18)   # hall ticket, separate
    row(160, 440, 22)   # name
    row(260, 440, 5)    # gender
    row(360, 440, 7)    # community
    # Vertical red line joining name/gender/community down the left.
    cv2.rectangle(img, (438, 160), (442, 400), RED, -1)
    return img


def test_tall_strip_splits_into_rows():
    img = _box_row_image()
    rows = find_box_rows(img)
    by_y = {r.y: r for r in rows}
    # Hall ticket row (separate contour) and the three joined rows.
    assert 120 in by_y and by_y[120].num_boxes == 18
    assert 180 in by_y and by_y[180].num_boxes == 22
    assert 280 in by_y and by_y[280].num_boxes == 5
    assert 380 in by_y and by_y[380].num_boxes == 7


def test_row_for_label_ignores_spaces():
    row = BoxRow(y=561, y1=541, y2=581, x1=440, x2=1283, box_w=42.0,
                 box_h=40.0, num_boxes=20, boxes=[])
    labels_spaceless = [{"text": "HALLTICKETNUMBER",
                         "norm": "hallticketnumber",
                         "cx": 268.0, "cy": 559.0, "x1": 166.0,
                         "x2": 370.0, "y1": 549.0, "y2": 569.0}]
    labels_spaced = [{"text": "HALL TICKET NUMBER",
                      "norm": "hall ticket number",
                      "cx": 268.0, "cy": 559.0, "x1": 166.0,
                      "x2": 370.0, "y1": 549.0, "y2": 569.0}]
    assert _row_for_label([row], labels_spaceless, "hall ticket") is row
    assert _row_for_label([row], labels_spaced, "hall ticket") is row


def _grid_ys(n, first=657.3, pitch=32.6):
    return [first + i * pitch for i in range(n)]


def _candidates(rows, pitch=33.0, first=673.5, per_row=5):
    """Candidate (x, y) points: `per_row` points per row, one row
    per entry of `rows` (a list of row indices)."""
    pts = []
    for i in rows:
        for k in range(per_row):
            pts.append((1000.0 + k * 30.0, first + i * pitch))
    return pts


def test_row_centres_few_clusters_fit_the_rows():
    """49 clusters for 50 rows, grid half a pitch off: the fitted
    rows must follow the real rows, with no stale grid value in a
    gap (the 388765 bug: grid row 1 kept 690)."""
    cands = _candidates(range(49))
    out = _row_centres_from_candidates(cands, 50,
                                       _grid_ys(50), tol=10.0)
    assert len(out) == 50
    assert abs(out[0] - 673.5) < 2.0
    assert abs(out[1] - 706.5) < 3.0  # was 690 (a gap) before the fix
    assert abs(out[2] - 739.5) < 3.0
    assert abs(out[48] - 673.5 - 48 * 33.0) < 3.0
    # The last row has no cluster: it takes the fitted value, not a
    # stale grid value.
    assert abs(out[49] - (673.5 + 49 * 33.0)) < 3.0


def test_row_centres_missing_middle_row():
    """A missing cluster in the middle must not shift the rows below
    it: they keep their own positions, the gap takes the fitted one."""
    cands = _candidates(list(range(25)) + list(range(26, 50)))
    out = _row_centres_from_candidates(cands, 50,
                                       _grid_ys(50), tol=10.0)
    assert len(out) == 50
    assert abs(out[24] - (673.5 + 24 * 33.0)) < 3.0
    assert abs(out[25] - (673.5 + 25 * 33.0)) < 5.0  # fitted gap row
    assert abs(out[26] - (673.5 + 26 * 33.0)) < 3.0
    assert abs(out[49] - (673.5 + 49 * 33.0)) < 3.0
