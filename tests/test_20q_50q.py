"""Tests for the 20Q daily-test and 50Q grand-test support.

The client sent two new sheet kinds that the dynamic reader could
not handle at all:
  * 20Q daily-test strip ("OMR ANSWER SHEET OF DAILY TEST"): a wide
    strip with 4 short columns of 5 rows, a B No / ID No / name table
    at the top right (values BELOW their labels), and a key PDF in a
    plain "SL NO / MARKS" text list (20 answers).
  * 50Q grand-test sheet ("OMR ANSWER SHEET OF GRAND TEST"): 50
    questions in 4 columns of 13/13/13/11, a key PDF in the same
    text-list format (50 answers, two printed columns that interleave
    in the text stream), and hard handwriting on the hall ticket /
    name that the reconciler must not let poison a good name match.
Both sheets have no timing marks, so the warp distorts them and the
deskewed-only copy is the correct input.
"""
import numpy as np
import pytest

from app.evaluation.answer_key import AnswerKeyExtractor
from app.omr.dynamic import (
    _find_answer_columns,
    _rows_per_column,
)
from app.ocr.engine import OCREngine

PINK = (200, 190, 235)  # BGR: R clearly above G and B (redness mask)
WHITE = (255, 255, 255)


# ---------------------------------------------------------------------------
# Rows per column
# ---------------------------------------------------------------------------

def test_rows_per_column_uneven_split():
    # 50 questions over 4 columns: the last column holds the
    # remainder (11), not 12 each (round(12.5) = 12 gave 48 rows).
    assert _rows_per_column(50, 4) == [13, 13, 13, 11]


def test_rows_per_column_even_splits_unchanged():
    assert _rows_per_column(200, 5) == [40, 40, 40, 40, 40]
    assert _rows_per_column(150, 3) == [50, 50, 50]
    assert _rows_per_column(160, 4) == [40, 40, 40, 40]
    assert _rows_per_column(20, 4) == [5, 5, 5, 5]


def test_rows_per_column_no_count_defaults_to_40():
    assert _rows_per_column(None, 4) == [40, 40, 40, 40]


# ---------------------------------------------------------------------------
# Short / wide answer columns (20Q strip)
# ---------------------------------------------------------------------------

def test_short_wide_columns_are_found():
    # Four 20Q columns: 280px wide, 210px tall on a 1650x563 strip
    # (17% of the page wide, 37% tall — wider than tall, so the old
    # "tall narrow column" test bh >= 3*bw rejected them).
    img = np.full((563, 1650, 3), WHITE, dtype=np.uint8)
    for x1 in (192, 500, 807, 1113):
        img[274:484, x1:x1 + 280] = PINK
    cols = _find_answer_columns(img, search_y1=185)
    assert len(cols) == 4
    assert [c[0] for c in cols] == [192, 500, 807, 1113]


def test_thin_horizontal_strip_is_not_a_column():
    # A short pink strip (a rule / underline) must not be accepted
    # as a column: it is far below the 20% page-height minimum.
    img = np.full((563, 1650, 3), WHITE, dtype=np.uint8)
    img[300:330, 192:472] = PINK
    assert _find_answer_columns(img, search_y1=185) == []


# ---------------------------------------------------------------------------
# Key PDF text-list parsing ("SL NO / MARKS")
# ---------------------------------------------------------------------------

def _make_list_key_pdf(path, pairs, two_columns=False):
    """Write a minimal PDF whose text is (question, answer) pairs."""
    import pymupdf
    doc = pymupdf.open()
    # Tall page so all pairs fit (a normal page overflows at ~50 lines).
    page = doc.new_page(width=595, height=2200)
    lines = ["T9", "SL NO", "MARKS"]
    if two_columns:
        # Two printed columns: left Q1..N/2, right the rest. The
        # text stream interleaves them row by row.
        half = len(pairs) // 2
        for i in range(half):
            lines.append(str(pairs[i][0]))
            lines.append(str(pairs[i][1]))
            lines.append(str(pairs[half + i][0]))
            lines.append(str(pairs[half + i][1]))
    else:
        for q, a in pairs:
            lines.append(str(q))
            lines.append(str(a))
    page.insert_text((72, 72), "\n".join(lines), fontsize=11)
    doc.save(path)
    doc.close()


def test_list_key_single_column(tmp_path):
    path = tmp_path / "T9.pdf"
    pairs = [(q, (q % 4) + 1) for q in range(1, 21)]
    _make_list_key_pdf(path, pairs)
    key = AnswerKeyExtractor().extract_from_pdf(path)
    assert len(key.items) == 20
    assert key.items[1] == "B" and key.items[20] == "A"
    assert sorted(key.items) == list(range(1, 21))


def test_list_key_two_columns_interleaved(tmp_path):
    # The T11 key: 50 answers in two printed columns; the text
    # stream reads (1, 26, 2, 27, ...) but each pair stays
    # consecutive, so all 50 must be recovered.
    path = tmp_path / "T11.pdf"
    pairs = [(q, (q % 4) + 1) for q in range(1, 51)]
    _make_list_key_pdf(path, pairs, two_columns=True)
    key = AnswerKeyExtractor().extract_from_pdf(path)
    assert len(key.items) == 50
    assert sorted(key.items) == list(range(1, 51))
    assert key.items[26] == "C" and key.items[50] == "C"


def test_list_key_rejects_incomplete_list(tmp_path):
    # A list with a gap (Q11 missing) is not a key: the caller must
    # fall through to grid detection, not accept a shifted parse.
    # (A list that covers Q=1..N exactly IS a valid N-question key,
    # so the rejection case needs a hole, not a short list.)
    path = tmp_path / "bad.pdf"
    pairs = [(q, (q % 4) + 1) for q in range(1, 21) if q != 11]
    _make_list_key_pdf(path, pairs)
    ext = AnswerKeyExtractor()
    import pymupdf
    doc = pymupdf.open(path)
    assert ext._extract_from_list_text(doc) == {}
    doc.close()


# ---------------------------------------------------------------------------
# Digit-less hall ticket must not poison the name match (50Q)
# ---------------------------------------------------------------------------

def test_digitless_hall_ticket_counts_as_absent():
    # PRIYA's hall ticket reads 'TAL' (no digits). The reconciler
    # must treat it as absent and use the name-only path, not let
    # the garbled HT drag a good name match below the bar.
    eng = OCREngine()
    roster = [{"roll": "T11-411", "name": "PRIYA"},
              {"roll": "T11-490", "name": "SUPRIYA"},
              {"roll": "T11-350", "name": "K VENKATARAMANA"}]
    assert eng._reconcile_with_roster("TAL", "PRIVA", "TAL", roster) == (
        "T11-411", "PRIYA")
    # The same garbled HT with a weak name still fails (no rescue).
    assert eng._reconcile_with_roster("TAL", "PRHNA", "TAL", roster) == (
        None, None)


def test_garbled_digit_hall_ticket_still_poisons_dual_signal():
    # SUPRIYA's HT has digits ('SUTTATRS440'), so the dual-signal
    # match runs and fails — the caller must fall back to the
    # name-only path itself (see the script), it is not fixed here.
    eng = OCREngine()
    roster = [{"roll": "T11-411", "name": "PRIYA"},
              {"roll": "T11-490", "name": "SUPRIYA"},
              {"roll": "T11-350", "name": "K VENKATARAMANA"}]
    assert eng._reconcile_with_roster(
        "SUTTATRS440", "SOPRIA", "SUTTATRS440", roster) == (None, None)
    # ... but the name alone resolves her.
    assert eng._reconcile_with_roster("", "SOPRIA", "", roster) == (
        "T11-490", "SUPRIYA")


# ---------------------------------------------------------------------------
# Daily-test (20Q) roster matching and helpers
# ---------------------------------------------------------------------------

def test_match_daily_test_lakshman_and_khyma():
    import sys
    sys.path.insert(0, ".")
    from extract_identities_to_excel import match_daily_test, _best_name_only_match, _roster_cell_str
    roster = [{"roll": "", "name": "LAKSHMAN", "bno": "T9", "idno": "011"},
              {"roll": "", "name": "K HYMA", "bno": "T15", "idno": "215"}]
    # LAKSHMAN: the ID No read is only '0' (thin '1's missed), but
    # the exact B No + name carry the match.
    assert match_daily_test("T9", "0", "LAKSHMAN", roster) == (
        "T9", "011", "LAKSHMAN")
    # K HYMA: the ID No '2' is read as '3', still matches.
    assert match_daily_test("T15", "315", "K HYMA", roster) == (
        "T15", "215", "K HYMA")
    # Nothing matching at all (wrong batch, wrong ID, wrong name)
    # matches nothing.
    assert match_daily_test("T99", "999", "UNKNOWN", roster) == (
        None, None, None)


def test_best_name_only_match_clear_winner():
    import sys
    sys.path.insert(0, ".")
    from extract_identities_to_excel import _best_name_only_match
    roster = [{"roll": "T11-411", "name": "PRIYA"},
              {"roll": "T11-490", "name": "SUPRIYA"},
              {"roll": "T11-350", "name": "K VENKATARAMANA"}]
    # 'PRHNA' is 0.60 vs PRIYA and 0.50 vs SUPRIYA: a clear winner
    # below the reconciler's 0.65 bar.
    assert _best_name_only_match("PRHNA", roster) == ("T11-411", "PRIYA")
    # Two students with the same name: no clear winner, so neither.
    dup_roster = [{"roll": "T11-411", "name": "PRIYA"},
                  {"roll": "T11-490", "name": "PRIYA"}]
    assert _best_name_only_match("PRHNA", dup_roster) == (None, None)
    # A name unlike anyone in the roster matches nobody.
    assert _best_name_only_match("XYZABC", roster) == (None, None)


def test_roster_cell_str_numeric_id():
    import sys
    sys.path.insert(0, ".")
    from extract_identities_to_excel import _roster_cell_str
    # Pandas reads the 3-box ID No 011 as the float 11.0.
    assert _roster_cell_str(11.0, pad_digits=3) == "011"
    assert _roster_cell_str("215.0", pad_digits=3) == "215"
    assert _roster_cell_str("T9") == "T9"
