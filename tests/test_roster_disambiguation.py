"""
Unit tests for Dual-Signal Roster Reconciler and Multi-Candidate Collision Disambiguation.
Ensures that students sharing identical suffix digits (e.g. 00015) are disambiguated
with 100% mathematical certainty using their district prefix and candidate name.
"""
import pytest
from app.ocr.engine import OCREngine

@pytest.fixture
def test_roster():
    return [
        {"roll": "KNL2025SGTS0015", "name": "R Krishna"},
        {"roll": "ATP2025SGTS00015", "name": "C Ramu"},
        {"roll": "CDVM2025SGTS00015", "name": "S ESWARA RAJU"},
        {"roll": "KNL2025SGTS00159", "name": "GOLLA SREENIVASULU"},
        {"roll": "", "name": "VENKATESH N"},
    ]

def test_identical_suffix_disambiguation_cdvm(test_roster):
    engine = OCREngine()
    # Sheet has CDVM2025SGTS00015 and candidate name S ESWARA RAJU
    r_ht, r_name = engine._reconcile_with_roster(
        candidate_ht="CDVM2025SGTS00015",
        candidate_name="S ESWARA RAJU",
        raw_ht="CDVM2025SGTS00015",
        roster=test_roster,
        secondary_roll="00015"
    )
    assert r_ht == "CDVM2025SGTS00015"
    assert r_name == "S ESWARA RAJU"

def test_identical_suffix_disambiguation_knl(test_roster):
    engine = OCREngine()
    # Sheet has KNL2025SGTS0015 and candidate name R Krishna
    r_ht, r_name = engine._reconcile_with_roster(
        candidate_ht="KNL2025SGTS0015",
        candidate_name="R KRISHNA",
        raw_ht="KNL2025SGTS0015",
        roster=test_roster,
        secondary_roll="0015"
    )
    assert r_ht == "KNL2025SGTS0015"
    assert r_name == "R Krishna"

def test_identical_suffix_disambiguation_atp(test_roster):
    engine = OCREngine()
    # Sheet has ATP2025SGTS00015 and candidate name C Ramu
    r_ht, r_name = engine._reconcile_with_roster(
        candidate_ht="ATP2025SGTS00015",
        candidate_name="C RAMU",
        raw_ht="ATP2025SGTS00015",
        roster=test_roster,
        secondary_roll="00015"
    )
    assert r_ht == "ATP2025SGTS00015"
    assert r_name == "C Ramu"

def test_mistaken_batch_prefix_co_verification(test_roster):
    engine = OCREngine()
    # If the folder prefix was mistakenly applied as KNL2025SGTS00015,
    # but the handwritten raw string is CDVM... and candidate name is S ESWARA RAJU
    r_ht, r_name = engine._reconcile_with_roster(
        candidate_ht="KNL2025SGTS00015",
        candidate_name="S ESWARA RAJU",
        raw_ht="CDVM2025SGTS00015",
        roster=test_roster,
        secondary_roll="00015"
    )
    assert r_ht == "CDVM2025SGTS00015"
    assert r_name == "S ESWARA RAJU"

def test_missing_ht_auto_population(test_roster):
    engine = OCREngine()
    # Sheet left HT completely blank, only wrote G SREENIVASULU
    r_ht, r_name = engine._reconcile_with_roster(
        candidate_ht="",
        candidate_name="G SREENIVASULU",
        raw_ht="",
        roster=test_roster,
        secondary_roll=""
    )
    assert r_ht == "KNL2025SGTS00159"
    assert r_name == "GOLLA SREENIVASULU"

def test_roster_empty_roll(test_roster):
    engine = OCREngine()
    # Candidate in roster has only Name and no Hall Ticket
    r_ht, r_name = engine._reconcile_with_roster(
        candidate_ht="",
        candidate_name="VENKATESH N",
        raw_ht="",
        roster=test_roster,
        secondary_roll=""
    )
    assert r_ht == ""
    assert r_name == "VENKATESH N"

def test_spot_admission_not_in_roster(test_roster):
    engine = OCREngine()
    # New walk-in student not in roster
    r_ht, r_name = engine._reconcile_with_roster(
        candidate_ht="",
        candidate_name="SURESH BABU",
        raw_ht="",
        roster=test_roster,
        secondary_roll=""
    )
    assert r_ht is None
    assert r_name is None

def test_b_devi_ocr_confusion_reconciliation():
    engine = OCREngine()
    roster = [
        {"roll": "KNL2025SGTS00105", "name": "B DEVI"},
        {"roll": "KNL2025SGTS00106", "name": "P THIRUMALA DEVI"},
        {"roll": "KNL2025SGTS00126", "name": "A UMA DEVI"},
    ]
    # Candidate wrote 'B Devi' (recognized as 'B EVRL' or 'BOEVR') with missing HT
    r_ht, r_name = engine._reconcile_with_roster(
        candidate_ht="",
        candidate_name="B EVRL",
        raw_ht="",
        roster=roster
    )
    assert r_ht == "KNL2025SGTS00105"
    assert r_name == "B DEVI"

    r_ht2, r_name2 = engine._reconcile_with_roster(
        candidate_ht="",
        candidate_name="BOEVR",
        raw_ht="",
        roster=roster
    )
    assert r_ht2 == "KNL2025SGTS00105"
    assert r_name2 == "B DEVI"

def test_b_mallikarjuna_multi_token_truncation_reconciliation():
    engine = OCREngine()
    roster = [
        {"roll": "KNL2025SGTS00121", "name": "B MALLIKARJUNA"},
        {"roll": "KNL2025SGTS00163", "name": "B CHINNA MAHESH"},
        {"roll": "KNL2025SGTS00140", "name": "B NAGARAJU"},
    ]
    # Candidate wrote 'BANGI CHINNA MALLIKARJU' (recognized as 'BAUNIC LUNAMAZLIKAA' or 'BAUOICULNNAMALLIKAAJY')
    r_ht, r_name = engine._reconcile_with_roster(
        candidate_ht="",
        candidate_name="BAUNIC LUNAMAZLIKAA",
        raw_ht="",
        roster=roster
    )
    assert r_ht == "KNL2025SGTS00121"
    assert r_name == "B MALLIKARJUNA"

    r_ht2, r_name2 = engine._reconcile_with_roster(
        candidate_ht="",
        candidate_name="BAUOICULNNAMALLIKAAJY",
        raw_ht="",
        roster=roster
    )
    assert r_ht2 == "KNL2025SGTS00121"
    assert r_name2 == "B MALLIKARJUNA"

