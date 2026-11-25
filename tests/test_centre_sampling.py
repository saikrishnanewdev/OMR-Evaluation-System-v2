"""Unit tests for centre sampling (the row-shift fix).

The bug: on the 200Q Syam sheet (img0076) the bubble grid's rows
sat ~25 px (almost one full row) below the real bubbles at the top
of each column — the grid pitch comes from the pink rectangle's
height, which runs past the last bubble row. So the reader sampled
the next row's marks: 7 lucky corrects and 17 near-miss blanks.

The fix: row y-centres come from the real detected circles,
clustered in top-to-bottom order (_row_centres_from_candidates).
Clusters in order cannot jump a row — the first cluster is the first
row, because no row can hide above it inside the column rectangle.

The 160Q sample (in the repo) is the regression anchor: dynamic
must still read it as 107 correct / 53 wrong / 0 unattempted
against the SA-08 key.
"""

from pathlib import Path

import cv2

from app.evaluation.answer_key import AnswerKeyExtractor
from app.evaluation.scoring_engine import ScoringEngine
from app.omr.dynamic import (
    _row_centres_from_candidates,
    analyze_sheet_dynamic,
    dynamic_rows_to_detected,
)
from app.omr.preprocessor import Preprocessor

REPO = Path(__file__).resolve().parent.parent
SAMPLE_IMG = REPO / "OMR_325601.jpg"
SAMPLE_KEY = REPO / "SA-08.pdf"


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
    # Row 10 takes the fitted value — the grid corrected by the
    # clusters' offset (grid + 3 here), not the stale grid value.
    # The stale grid value is what broke the 150Q sheet 388765: its
    # grid sat half a pitch off the real rows, so the missing row
    # kept a value in the gap between two real rows and every row
    # below it shifted by one.
    assert abs(got[10] - rows[10]) <= 2.0
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


def test_dynamic_160q_sample_scores_107():
    """Regression anchor: the real filled 160Q sample must still
    read 107 correct / 53 wrong / 0 unattempted against the SA-08
    key (the documented benchmark)."""
    img = cv2.imread(str(SAMPLE_IMG))
    assert img is not None
    aligned, _angle = Preprocessor.align_and_deskew(img)
    dyn = analyze_sheet_dynamic(aligned, expected_questions=160,
                                ocr_engine=None)
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
