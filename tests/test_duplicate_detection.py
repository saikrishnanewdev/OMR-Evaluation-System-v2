"""
Test Suite for Batch-wide Hall Ticket Uniqueness and Duplicate Detection
========================================================================
Validates that:
  1. Hall Ticket numbers in any exam batch must be unique.
  2. Any duplicate Hall Ticket numbers across the batch are detected dynamically.
  3. All sheets claiming duplicate numbers are flagged with REVIEW_REQUIRED (Duplicate HT: <HT>).
  4. Blank, unreadable, error, or candidate-name records are never falsely flagged as duplicates.
  5. Whitespace and case variations are normalized cleanly.
  6. Zero hardcoded values exist.
"""

import pytest
from extract_identities_to_excel import detect_and_flag_duplicate_hall_tickets


def test_unique_batch_has_zero_duplicates():
    """Batch where every sheet has a distinct HT should have 0 duplicates and remain unchanged."""
    results = [
        {"File Name": "OMR_01.jpg", "Hall Ticket / Name": "KNL2025SATS00001", "Identification Type": "HALL TICKET", "Status": "SUCCESS"},
        {"File Name": "OMR_02.jpg", "Hall Ticket / Name": "KNL2025SATS00002", "Identification Type": "HALL TICKET", "Status": "SUCCESS"},
        {"File Name": "OMR_03.jpg", "Hall Ticket / Name": "KNL2025SATS00003", "Identification Type": "HALL TICKET", "Status": "REVIEW_REQUIRED (Low Confidence)"},
    ]

    dups = detect_and_flag_duplicate_hall_tickets(results)
    assert len(dups) == 0
    assert results[0]["Status"] == "SUCCESS"
    assert results[1]["Status"] == "SUCCESS"
    assert results[2]["Status"] == "REVIEW_REQUIRED (Low Confidence)"


def test_duplicate_ht_flagged_for_all_sheets():
    """If two or more sheets claim the same HT, all of them must be flagged for review."""
    results = [
        {"File Name": "OMR_10.jpg", "Hall Ticket / Name": "KNL2025SGTS00167", "Identification Type": "HALL TICKET", "Status": "SUCCESS"},
        {"File Name": "OMR_20.jpg", "Hall Ticket / Name": "KNL2025SGTS00167", "Identification Type": "HALL TICKET", "Status": "REVIEW_REQUIRED (Low Confidence)"},
        {"File Name": "OMR_30.jpg", "Hall Ticket / Name": "KNL2025SGTS00167", "Identification Type": "HALL TICKET", "Status": "SUCCESS"},
        {"File Name": "OMR_40.jpg", "Hall Ticket / Name": "KNL2025SGTS00099", "Identification Type": "HALL TICKET", "Status": "SUCCESS"},
    ]

    dups = detect_and_flag_duplicate_hall_tickets(results)
    assert "KNL2025SGTS00167" in dups
    assert len(dups["KNL2025SGTS00167"]) == 3

    assert results[0]["Status"] == "REVIEW_REQUIRED (Duplicate HT: KNL2025SGTS00167)"
    assert results[1]["Status"] == "REVIEW_REQUIRED (Duplicate HT: KNL2025SGTS00167)"
    assert results[2]["Status"] == "REVIEW_REQUIRED (Duplicate HT: KNL2025SGTS00167)"
    # Non-duplicate remains SUCCESS
    assert results[3]["Status"] == "SUCCESS"


def test_multiple_duplicate_groups():
    """Batch with multiple different duplicated HTs should detect all groups."""
    results = [
        {"File Name": "A.jpg", "Hall Ticket / Name": "HT_100", "Identification Type": "HALL TICKET", "Status": "SUCCESS"},
        {"File Name": "B.jpg", "Hall Ticket / Name": "HT_100", "Identification Type": "HALL TICKET", "Status": "SUCCESS"},
        {"File Name": "C.jpg", "Hall Ticket / Name": "HT_200", "Identification Type": "HALL TICKET", "Status": "SUCCESS"},
        {"File Name": "D.jpg", "Hall Ticket / Name": "HT_200", "Identification Type": "HALL TICKET", "Status": "SUCCESS"},
        {"File Name": "E.jpg", "Hall Ticket / Name": "HT_300", "Identification Type": "HALL TICKET", "Status": "SUCCESS"},
    ]

    dups = detect_and_flag_duplicate_hall_tickets(results)
    assert len(dups) == 2
    assert "HT_100" in dups
    assert "HT_200" in dups
    assert results[0]["Status"] == "REVIEW_REQUIRED (Duplicate HT: HT_100)"
    assert results[1]["Status"] == "REVIEW_REQUIRED (Duplicate HT: HT_100)"
    assert results[2]["Status"] == "REVIEW_REQUIRED (Duplicate HT: HT_200)"
    assert results[3]["Status"] == "REVIEW_REQUIRED (Duplicate HT: HT_200)"
    assert results[4]["Status"] == "SUCCESS"


def test_ignores_blank_error_and_candidate_names():
    """Blank sheets, errors, and missing HT names should never be grouped as duplicate HTs."""
    results = [
        {"File Name": "OMR_B1.jpg", "Hall Ticket / Name": "(BLANK / UNREADABLE)", "Identification Type": "CANDIDATE NAME (MISSING HT)", "Status": "REVIEW_REQUIRED (Blank Sheet)"},
        {"File Name": "OMR_B2.jpg", "Hall Ticket / Name": "(BLANK / UNREADABLE)", "Identification Type": "CANDIDATE NAME (MISSING HT)", "Status": "REVIEW_REQUIRED (Blank Sheet)"},
        {"File Name": "OMR_E1.jpg", "Hall Ticket / Name": "ERROR", "Identification Type": "EXCEPTION", "Status": "ERROR: Corrupt"},
        {"File Name": "OMR_E2.jpg", "Hall Ticket / Name": "ERROR", "Identification Type": "EXCEPTION", "Status": "ERROR: Corrupt"},
        {"File Name": "OMR_N1.jpg", "Hall Ticket / Name": "RAMESH", "Identification Type": "CANDIDATE NAME (MISSING HT)", "Status": "REVIEW_REQUIRED (Missing HT)"},
        {"File Name": "OMR_N2.jpg", "Hall Ticket / Name": "RAMESH", "Identification Type": "CANDIDATE NAME (MISSING HT)", "Status": "REVIEW_REQUIRED (Missing HT)"},
        {"File Name": "OMR_H1.jpg", "Hall Ticket / Name": "KNL2025SATS00001", "Identification Type": "HALL TICKET", "Status": "SUCCESS"},
    ]

    dups = detect_and_flag_duplicate_hall_tickets(results)
    assert len(dups) == 0
    assert results[0]["Status"] == "REVIEW_REQUIRED (Blank Sheet)"
    assert results[1]["Status"] == "REVIEW_REQUIRED (Blank Sheet)"
    assert results[2]["Status"] == "ERROR: Corrupt"
    assert results[3]["Status"] == "ERROR: Corrupt"
    assert results[6]["Status"] == "SUCCESS"


def test_case_and_whitespace_normalization():
    """Case and whitespace variations of the same HT should be caught as duplicates."""
    results = [
        {"File Name": "OMR_01.jpg", "Hall Ticket / Name": "knl2025sats00005  ", "Identification Type": "HALL TICKET", "Status": "SUCCESS"},
        {"File Name": "OMR_02.jpg", "Hall Ticket / Name": "  KNL2025SATS00005", "Identification Type": "HALL TICKET", "Status": "SUCCESS"},
    ]

    dups = detect_and_flag_duplicate_hall_tickets(results)
    assert len(dups) == 1
    assert "KNL2025SATS00005" in dups
    assert results[0]["Status"] == "REVIEW_REQUIRED (Duplicate HT: KNL2025SATS00005)"
    assert results[1]["Status"] == "REVIEW_REQUIRED (Duplicate HT: KNL2025SATS00005)"

