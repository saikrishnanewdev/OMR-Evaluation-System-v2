"""Tests for the dynamic-only identity vote (OMR_348819 fix).

Two readings of the same hall-ticket row can disagree: the primary
read of 348819 is 'KKD2025K7300694' while the second read (a taller
strip, catching handwriting that dips below the detected row) is
'KKD2025KTS01624' (the sheet says KKD2025KTS01627). The vote lets
the roster decide, and a reconciliation is only trusted when the
roster student's name matches the sheet's own name read strongly
(>= 0.70) — otherwise the raw reading stands, because a garbled
hall ticket is honest and a wrong student is not.
"""
import pytest

from app.ocr.engine import OCREngine, _digit_agreement


@pytest.fixture
def roster_348819():
    return [
        {"roll": "KKD2025KTS01627", "name": "CH ANIL KUMAR"},
        {"roll": "KKD2025KTS00645", "name": ""},
        {"roll": "KKD2025KTS00694", "name": "KOTA HEMANT"},
        {"roll": "KKD2025KTS04954", "name": "SOME STUDENT"},
        {"roll": "KKD2025KTS00211", "name": "KURUVA NAVEEN KUMAR"},
        {"roll": "KKD2025KTS00221", "name": "GUDIPALLI RAKESH"},
        {"roll": "KKD2025KTS01562", "name": "CHANDAKA SURENDRA"},
    ]


def test_digit_agreement_is_position_wise():
    # '01624' vs the true '01627' is one digit off: 0.8.
    assert _digit_agreement("01624", "01627") == 0.8
    # '01624' vs '01562' shares digits out of place, so a
    # SequenceMatcher-style ratio would call it 0.8 too; position-wise
    # only '01' agree: 0.4. This is what stops the wrong student
    # (CHANDAKA SURENDRA, 01562) winning the 348819 vote.
    assert _digit_agreement("01624", "01562") == 0.4
    assert _digit_agreement("00694", "00694") == 1.0
    assert _digit_agreement("", "01627") == 0.0


def test_blank_name_row_rejected_on_fuzzy_ht(roster_348819):
    engine = OCREngine()
    # The garbled dynamic read must NOT steal the nameless 00645 row.
    r_ht, r_name = engine._reconcile_with_roster(
        candidate_ht="KKD2025K7300694",
        candidate_name="CHANTKUMAG",
        raw_ht="KKD2025K7300694",
        roster=roster_348819,
        preferred_prefix="KKD2025KTS",
    )
    assert r_ht != "KKD2025KTS00645"


def test_blank_name_row_accepted_on_exact_ht(roster_348819):
    engine = OCREngine()
    # An exactly-read hall ticket may still use a nameless roster row.
    r_ht, r_name = engine._reconcile_with_roster(
        candidate_ht="KKD2025KTS00645",
        candidate_name="SOME NAME",
        raw_ht="KKD2025KTS00645",
        roster=roster_348819,
        preferred_prefix="KKD2025KTS",
    )
    assert r_ht == "KKD2025KTS00645"


def test_vote_picks_second_on_348819(roster_348819):
    engine = OCREngine()
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="KKD2025K7300694", dyn_name="CHANTKUMAG",
        second_ht="KKD2025KTS01624",
        roster=roster_348819, preferred_prefix="KKD2025KTS")
    assert source == "second"
    assert ht == "KKD2025KTS01627"
    assert name == "CH ANIL KUMAR"


def test_vote_rejects_second_on_388773(roster_348819):
    engine = OCREngine()
    # The second reading leads to GUDIPALLI RAKESH (00221), whose
    # name only scores 0.64 against the sheet's 'GRUDRAKSHI' — below
    # the 0.70 gate — so it is rejected and the primary reading stands.
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="K2025T00211", dyn_name="GRUDRAKSHI",
        second_ht="KD2025T500211",
        roster=roster_348819, preferred_prefix="KKD2025KTS")
    assert source == "dynamic"
    assert ht == "K2025T00211"
    assert name == "GRUDRAKSHI"


def test_vote_keeps_dynamic_when_readings_agree(roster_348819):
    engine = OCREngine()
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="KKD2025KTS01627", dyn_name="CH ANIL KUMAR",
        second_ht="KKD2025KTS01627",
        roster=roster_348819, preferred_prefix="KKD2025KTS")
    assert source == "dynamic"
    assert ht == "KKD2025KTS01627"
    assert name == "CH ANIL KUMAR"


def test_vote_keeps_dynamic_when_neither_matches_roster():
    engine = OCREngine()
    # img0076-style: the student is not in the roster at all.
    roster = [{"roll": "KKD2025KTS00001", "name": "SOMEONE ELSE"}]
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="AP05C1798", dyn_name="SAIKRSHNA",
        second_ht="AP05C01798",
        roster=roster, preferred_prefix="AP05CJ")
    assert source == "dynamic"
    assert ht == "AP05C1798"
    assert name == "SAIKRSHNA"


def test_vote_keeps_dynamic_without_roster():
    engine = OCREngine()
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="KKD2025K7300694", dyn_name="CHANTKUMAG",
        second_ht="KKD2025KTS01624",
        roster=None, preferred_prefix="KKD2025KTS")
    assert source == "dynamic"
    assert ht == "KKD2025K7300694"


def test_vote_picks_dynamic_when_dynamic_wins(roster_348819):
    engine = OCREngine()
    # Dynamic read the sheet right; the second reading is wrong.
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="KKD2025KTS01627", dyn_name="CH ANIL KUMAR",
        second_ht="KKD2025KTS00645",
        roster=roster_348819, preferred_prefix="KKD2025KTS")
    assert source == "dynamic"
    assert ht == "KKD2025KTS01627"
    assert name == "CH ANIL KUMAR"


def test_vote_returns_raw_when_no_reconciliation_is_trusted(roster_348819):
    engine = OCREngine()
    # No second reading, and the primary's reconciliation (00694,
    # KOTA HEMANT) has a name score of only 0.45 against the sheet's
    # 'CHANTKUMAG' — below the 0.70 gate — so the raw reading stands
    # instead of the wrong student.
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="KKD2025K7300694", dyn_name="CHANTKUMAG",
        second_ht="",
        roster=roster_348819, preferred_prefix="KKD2025KTS")
    assert source == "dynamic"
    assert ht == "KKD2025K7300694"
    assert name == "CHANTKUMAG"


def test_vote_second_only_when_dynamic_has_no_name(roster_348819):
    engine = OCREngine()
    # Primary found no hall ticket and no usable name; the second
    # reading is an exact roster hall ticket, so it wins.
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="", dyn_name="",
        second_ht="KKD2025KTS01627",
        roster=roster_348819, preferred_prefix="KKD2025KTS")
    assert source == "second"
    assert ht == "KKD2025KTS01627"
    assert name == "CH ANIL KUMAR"


def test_vote_name_only_lookup_still_finds_student(roster_348819):
    engine = OCREngine()
    # Primary found the name but no hall ticket: the name-only
    # reconciliation finds the student, so the dynamic reading stands.
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="", dyn_name="CH ANIL KUMAR",
        second_ht="",
        roster=roster_348819, preferred_prefix="KKD2025KTS")
    assert source == "dynamic"
    assert ht == "KKD2025KTS01627"
    assert name == "CH ANIL KUMAR"
