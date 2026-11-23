"""Unit tests for the Reading Mode toggle (auto / dynamic / fixed).

The batch script (extract_identities_to_excel.py) and the app's batch
UI let the user pick how a folder of sheets is read:
- auto: dynamic only when the warped top is cut off, fixed otherwise
  (the behaviour before the toggle existed).
- dynamic: always try dynamic first, fall back to fixed.
- fixed: never use dynamic.
The mode actually used for each sheet is recorded in the
"Reading Mode" column of the Excel output, so the user can compare
runs sheet by sheet.

Uses the 160Q sample (OMR_325601.jpg + SA-08.pdf, benchmark
107/53/0, 53.50 marks) — its top is intact, so auto must behave like
fixed there, and dynamic must still score the same.
"""

import shutil
from pathlib import Path

import openpyxl

from extract_identities_to_excel import (
    export_results_to_excel,
    process_folder,
)

REPO = Path(__file__).resolve().parent.parent
SAMPLE_IMG = REPO / "OMR_325601.jpg"
SAMPLE_KEY = REPO / "SA-08.pdf"


def _folder_with_sample(tmp_path):
    shutil.copy(SAMPLE_IMG, tmp_path / SAMPLE_IMG.name)
    shutil.copy(SAMPLE_KEY, tmp_path / SAMPLE_KEY.name)
    return tmp_path


def _run(mode, tmp_path):
    folder = _folder_with_sample(tmp_path)
    ok, results, _ = process_folder(
        folder, reading_mode=mode,
        output_excel=tmp_path / f"out_{mode}.xlsx",
    )
    assert ok is True
    assert len(results) == 1
    return results[0]


def test_mode_fixed_uses_fixed_template(tmp_path):
    rec = _run("fixed", tmp_path)
    assert rec["Reading Mode"] == "Fixed"
    assert rec["Correct"] == 107
    assert rec["Wrong"] == 53
    assert rec["Unattempted"] == 0
    assert rec["Total Marks"] == 53.50


def test_mode_dynamic_scores_same_on_160q(tmp_path):
    rec = _run("dynamic", tmp_path)
    assert rec["Reading Mode"] == "Dynamic"
    assert rec["Correct"] == 107
    assert rec["Wrong"] == 53
    assert rec["Unattempted"] == 0
    assert rec["Total Marks"] == 53.50


def test_mode_auto_uses_fixed_when_top_intact(tmp_path):
    # The 160Q sample's top is intact, so auto must behave like fixed.
    rec = _run("auto", tmp_path)
    assert rec["Reading Mode"] == "Fixed"
    assert rec["Correct"] == 107
    assert rec["Unattempted"] == 0


def test_invalid_mode_falls_back_to_auto(tmp_path):
    rec = _run("bogus", tmp_path)
    assert rec["Reading Mode"] == "Fixed"
    assert rec["Correct"] == 107


def test_excel_output_includes_reading_mode_column(tmp_path):
    out = tmp_path / "out.xlsx"
    export_results_to_excel(
        results=[{
            "File Name": "img0076.jpg",
            "Hall Ticket / Name": "AP05C1798",
            "Identification Type": "HALL TICKET",
            "Reading Mode": "Dynamic",
            "Total Marks": 46.0,
            "Correct": 46,
            "Correct Marks": 46.0,
            "Wrong": 154,
            "Wrong Marks": 0.0,
            "Unattempted": 0,
            "Unattempted Marks": 0.0,
            "Confidence %": 0.9,
            "Status": "SUCCESS",
        }],
        output_excel=out,
        target_folder=tmp_path,
        has_evaluation=True,
    )
    ws = openpyxl.load_workbook(out).active
    headers = [c.value for c in ws[1]]
    assert "Reading Mode" in headers
    row = [c.value for c in ws[2]]
    assert row[headers.index("Reading Mode")] == "Dynamic"
    assert row[headers.index("Hall Ticket / Name")] == "AP05C1798"
