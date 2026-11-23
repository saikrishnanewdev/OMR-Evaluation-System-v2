"""Unit tests for centre sampling (the row-shift fix).

The bug: the fixed template's rows sat ~25 px (almost one full row)
below the real bubbles at the top of each column on the 200Q Syam
sheet (img0076) — its base y (1151) does not match the sheet (first
real row ~1123.5). So the fixed reader sampled the next row's marks:
7 lucky corrects and 17 near-miss blanks. The dynamic grid had the
same weakness in principle (its pitch comes from the pink rectangle's
height, which runs past the last bubble row).

The fix: row y-centres come from the real detected circles,
clustered in top-to-bottom order (_row_centres_from_candidates).
Clusters in order cannot jump a row — the first cluster is the first
row, because no row can hide above it inside the column rectangle.

On img0076 this makes fixed and dynamic agree on all 200 questions
(46/154/0 in both modes, 0 disagreements, verified locally — the
sheet itself is real candidate data and is not in the repo). The
160Q sample (in the repo) must not change: its template grid is
already right, so centre sampling must return the same answers.
"""

from pathlib import Path

import cv2

from app.omr.bubble_detector import BubbleDetector
from app.omr.dynamic import _row_centres_from_candidates
from app.omr.preprocessor import Preprocessor
from app.omr.template import get_template

REPO = Path(__file__).resolve().parent.parent
SAMPLE_IMG = REPO / "OMR_325601.jpg"


def _grid(n=40, base=1000.0, pitch=29.0):
    return [base + i * pitch for i in range(n)]


def _cands(rows, per_row=4, jitter=1.0):
    """Candidate (x, y) points for the given row y's."""
    out = []
    for y in rows:
        for k in range(per_row):
            out.append((100.0 + k * 30.0, y + (jitter if k % 2 else -jitter)))
    return out


def test_exact_clusters_map_in_order():
    grid = _grid()
    rows = [g + 3.0 for g in grid]  # grid a few px off — order still wins
    got = _row_centres_from_candidates(_cands(rows), 40, grid)
    assert len(got) == 40
    for i, y in enumerate(got):
        assert abs(y - rows[i]) <= 2.0


def test_missing_cluster_falls_back_to_grid():
    grid = _grid()
    rows = [g + 3.0 for g in grid]
    missing = rows[:10] + rows[11:]  # row 10 has no candidates
    got = _row_centres_from_candidates(_cands(missing), 40, grid)
    assert len(got) == 40
    # Row 10 keeps the grid value; its neighbours use the clusters.
    assert abs(got[10] - grid[10]) < 1e-6
    assert abs(got[9] - rows[9]) <= 2.0
    assert abs(got[11] - rows[11]) <= 2.0


def test_extra_cluster_is_dropped():
    grid = _grid()
    rows = [g + 3.0 for g in grid]
    # A spurious cluster (one stray candidate) between rows 5 and 6.
    cands = _cands(rows) + [(200.0, rows[5] + 14.0)]
    got = _row_centres_from_candidates(cands, 40, grid)
    assert len(got) == 40
    for i, y in enumerate(got):
        assert abs(y - rows[i]) <= 2.0


def test_no_candidates_returns_grid():
    grid = _grid()
    got = _row_centres_from_candidates([], 40, grid)
    assert got == grid


def test_fixed_detector_unchanged_on_160q_when_grid_is_right():
    """Centre sampling must not change answers where the template
    grid is already right (the 160Q sample): with and without
    image_bgr, the fixed detector must read every question the same.
    """
    img = cv2.imread(str(SAMPLE_IMG))
    left_marks, right_marks, _angle = Preprocessor.detect_timing_tracks(img)
    aligned, _angle = Preprocessor.align_and_deskew(img)
    ink_map = Preprocessor.extract_ink_channel(aligned)
    detector = BubbleDetector(template=get_template(160))
    plain = detector.analyze_sheet(
        ink_map, timing_marks=(left_marks, right_marks))
    sampled = detector.analyze_sheet(
        ink_map, timing_marks=(left_marks, right_marks),
        image_bgr=aligned)
    assert len(plain) == len(sampled) == 160
    for q in range(1, 161):
        assert sampled[q]["detected_option"] == plain[q]["detected_option"], \
            f"Q{q} changed with centre sampling"
