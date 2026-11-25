"""Tests for the identity vote (OMR_348819 fix).

Dynamic and fixed readers can disagree on the same sheet: dynamic
read 'KKD2025K7300694' on 348819 while fixed read 'KKD2025KTS00627'
(the sheet says KKD2025KTS01627). The vote lets the roster decide,
and a roster row with no name may not win on a fuzzy hall ticket.
"""
import pytest

from app.ocr.engine import OCREngine


@pytest.fixture
def roster_348819():
    return [
        {"roll": "KKD2025KTS01627", "name": "CH ANIL KUMAR"},
        {"roll": "KKD2025KTS00645", "name": ""},
        {"roll": "KKD2025KTS00694", "name": "KOTA HEMANT"},
        {"roll": "KKD2025KTS04954", "name": "SOME STUDENT"},
    ]


def test_blank_name_row_rejected_on_fuzzy_ht(roster_348819):
    engine = OCREngine()
    # The garbled dynamic read must NOT steal the nameless 00645 row.
    # (It may still land on 00694, whose digits match exactly — that is
    # what the vote's name check rejects; see test_vote_picks_fixed.)
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


def test_vote_picks_fixed_on_348819(roster_348819):
    engine = OCREngine()
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="KKD2025K7300694", dyn_name="CHANTKUMAG",
        fixed_ht="KKD2025KTS00627", fixed_name="CHANTIKUMAG",
        roster=roster_348819, preferred_prefix="KKD2025KTS")
    assert source == "fixed"
    assert ht == "KKD2025KTS01627"
    assert name == "CH ANIL KUMAR"


def test_vote_keeps_dynamic_when_readings_agree(roster_348819):
    engine = OCREngine()
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="KKD2025KTS01627", dyn_name="CH ANIL KUMAR",
        fixed_ht="KKD2025KTS01627", fixed_name="CH ANIL KUMAR",
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
        fixed_ht="", fixed_name="AIKRSHNA",
        roster=roster, preferred_prefix="AP05CJ")
    assert source == "dynamic"
    assert ht == "AP05C1798"
    assert name == "SAIKRSHNA"


def test_vote_keeps_dynamic_without_roster():
    engine = OCREngine()
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="KKD2025K7300694", dyn_name="CHANTKUMAG",
        fixed_ht="KKD2025KTS00627", fixed_name="CHANTIKUMAG",
        roster=None, preferred_prefix="KKD2025KTS")
    assert source == "dynamic"
    assert ht == "KKD2025K7300694"


def test_vote_picks_dynamic_when_dynamic_wins(roster_348819):
    engine = OCREngine()
    # Dynamic read the sheet right; fixed misread it.
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="KKD2025KTS01627", dyn_name="CH ANIL KUMAR",
        fixed_ht="KKD2025KTS00645", fixed_name="",
        roster=roster_348819, preferred_prefix="KKD2025KTS")
    assert source == "dynamic"
    assert ht == "KKD2025KTS01627"
    assert name == "CH ANIL KUMAR"


def test_vote_takes_fixed_ht_when_dynamic_has_name_only(roster_348819):
    engine = OCREngine()
    # Dynamic found no usable name and no hall ticket; fixed found a
    # hall ticket and the roster confirms it.
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="", dyn_name="XYZABC",
        fixed_ht="KKD2025KTS00627", fixed_name="CH ANIL KUMAR",
        roster=roster_348819, preferred_prefix="KKD2025KTS")
    assert source == "fixed"
    assert ht == "KKD2025KTS01627"
    assert name == "CH ANIL KUMAR"


def test_vote_name_only_lookup_still_finds_student(roster_348819):
    engine = OCREngine()
    # Dynamic found the name but no hall ticket: the name-only
    # reconciliation finds the student, so the dynamic reading stands.
    ht, name, source = engine.resolve_identity_vote(
        dyn_ht="", dyn_name="CH ANIL KUMAR",
        fixed_ht="KKD2025KTS00627", fixed_name="",
        roster=roster_348819, preferred_prefix="KKD2025KTS")
    assert source == "dynamic"
    assert ht == "KKD2025KTS01627"
    assert name == "CH ANIL KUMAR"
