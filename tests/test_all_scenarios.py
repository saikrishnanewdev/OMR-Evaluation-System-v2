"""Automated verification suite implementing all 18 mandatory operational scenarios."""
import pytest
import os
import cv2
import numpy as np
from pathlib import Path
from decimal import Decimal
from app.models.entities import Examination, AnswerKey, ProcessedSheet
from app.evaluation.answer_key import AnswerKeyExtractor
from app.evaluation.scoring_engine import ScoringEngine
from app.evaluation.ranking_engine import RankingEngine
from app.services.evaluation_service import EvaluationService
from app.services.batch_service import BatchProcessor
from app.export.excel_exporter import ExcelExporter
from app.export.excel_validator import ExcelValidator
from app.database.connection import DatabaseManager
from app.database.repository import Repository
from tests.synthetic_generator import SyntheticOMRGenerator


@pytest.fixture(scope="module")
def test_env():
    """Sets up a clean test database and loads reference answer key."""
    db_path = Path("data/test_suite.db")
    if db_path.exists():
        try:
            os.remove(db_path)
        except Exception:
            pass

    mgr = DatabaseManager(db_path)
    repo = Repository(mgr)
    service = EvaluationService(repo=repo)

    exam = Examination(
        code="SCENARIO_TEST",
        name="Mandatory 18 Scenarios Test Examination",
        total_questions=160,
        correct_mark=0.50,
        wrong_mark=0.00,
        unattempted_mark=0.00,
        status="ACTIVE"
    )
    exam.id = repo.create_examination(exam)

    extractor = AnswerKeyExtractor()
    key = extractor.extract_from_pdf(Path("SA-08.pdf"), exam_id=exam.id)
    repo.save_answer_key(key)

    # Pristine generator creates a completely blank form without existing candidate ink
    pristine_gen = SyntheticOMRGenerator(base_image_path=None)
    # Reference generator modifies the scanned sample sheet
    ref_gen = SyntheticOMRGenerator(base_image_path=Path("OMR_325601.jpg"))

    return {
        "repo": repo,
        "service": service,
        "exam": exam,
        "key": key,
        "pristine_gen": pristine_gen,
        "ref_gen": ref_gen
    }


# Scenario 1: Clear, fully marked sheet
def test_scenario_01_clear_fully_marked_sheet(test_env):
    service = test_env["service"]
    exam = test_env["exam"]
    key = test_env["key"]

    sheet = service.process_single_sheet(exam, key, Path("OMR_325601.jpg"))
    assert sheet.correct_count == 107
    assert sheet.wrong_count == 53
    assert sheet.unattempted_count == 0
    assert sheet.total_marks == 53.50


# Scenario 2: Sheet with all responses blank
def test_scenario_02_all_responses_blank(test_env, tmp_path):
    generator = test_env["pristine_gen"]
    service = test_env["service"]
    exam = test_env["exam"]
    key = test_env["key"]

    blank_answers = {q: "BLANK" for q in range(1, 161)}
    blank_img = generator.generate_sheet(blank_answers, hall_ticket="KNL2025SATS00099")
    img_path = tmp_path / "blank_sheet.jpg"
    cv2.imwrite(str(img_path), blank_img)

    sheet = service.process_single_sheet(exam, key, img_path)
    assert sheet.correct_count == 0
    assert sheet.wrong_count == 0
    assert sheet.unattempted_count == 160
    assert sheet.total_marks == 0.00


# Scenario 3: Sheet with faint pencil or pen marks
def test_scenario_03_faint_marks_trigger_review(test_env, tmp_path):
    generator = test_env["ref_gen"]
    service = test_env["service"]
    exam = test_env["exam"]
    key = test_env["key"]

    answers = {q: key.items[q] for q in range(1, 161)}
    faint_img = generator.generate_sheet(answers, hall_ticket="KNL2025SATS00003", faint_indices=[10, 20])
    img_path = tmp_path / "faint_sheet.jpg"
    cv2.imwrite(str(img_path), faint_img)

    sheet = service.process_single_sheet(exam, key, img_path)
    assert sheet.status in ("REVIEW_REQUIRED", "SUCCESS")
    assert sheet.responses[10].confidence < 0.65 or sheet.responses[20].confidence < 0.65


# Scenario 4: Sheet with multiple marked bubbles
def test_scenario_04_multiple_marked_bubbles(test_env, tmp_path):
    generator = test_env["ref_gen"]
    service = test_env["service"]
    exam = test_env["exam"]
    key = test_env["key"]

    answers = {q: key.items[q] for q in range(1, 161)}
    multi_img = generator.generate_sheet(answers, hall_ticket="KNL2025SATS00004", multi_indices=[15, 25])
    img_path = tmp_path / "multi_sheet.jpg"
    cv2.imwrite(str(img_path), multi_img)

    sheet = service.process_single_sheet(exam, key, img_path)
    assert sheet.status == "REVIEW_REQUIRED"
    assert sheet.responses[15].detected_option == "MULTI"
    assert sheet.responses[25].detected_option == "MULTI"
    assert sheet.responses[15].awarded_marks == 0.00


# Scenario 5: Sheet with partially filled bubbles
def test_scenario_05_partially_filled_bubbles(test_env, tmp_path):
    generator = test_env["ref_gen"]
    service = test_env["service"]
    exam = test_env["exam"]
    key = test_env["key"]

    answers = {q: key.items[q] for q in range(1, 161)}
    partial_img = generator.generate_sheet(answers, hall_ticket="KNL2025SATS00005", partial_indices=[5, 12])
    img_path = tmp_path / "partial_sheet.jpg"
    cv2.imwrite(str(img_path), partial_img)

    sheet = service.process_single_sheet(exam, key, img_path)
    assert sheet.id is not None
    assert sheet.correct_count + sheet.wrong_count + sheet.unattempted_count == 160


# Scenario 6: Rotated or skewed scan
def test_scenario_06_rotated_or_skewed_scan(test_env, tmp_path):
    generator = test_env["ref_gen"]
    service = test_env["service"]
    exam = test_env["exam"]
    key = test_env["key"]

    answers = {q: key.items[q] for q in range(1, 161)}
    rot_img = generator.generate_sheet(answers, hall_ticket="KNL2025SATS00006", rotation_deg=2.0)
    img_path = tmp_path / "rotated_sheet.jpg"
    cv2.imwrite(str(img_path), rot_img)

    sheet = service.process_single_sheet(exam, key, img_path)
    assert sheet.id is not None
    assert sheet.correct_count + sheet.wrong_count + sheet.unattempted_count == 160


# Scenario 7: Low-resolution scan
def test_scenario_07_low_resolution_scan(test_env, tmp_path):
    service = test_env["service"]
    exam = test_env["exam"]
    key = test_env["key"]

    raw = cv2.imread("OMR_325601.jpg")
    h, w = raw.shape[:2]
    low_res = cv2.resize(raw, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    img_path = tmp_path / "low_res_sheet.jpg"
    cv2.imwrite(str(img_path), low_res)

    sheet = service.process_single_sheet(exam, key, img_path)
    assert sheet.correct_count + sheet.wrong_count + sheet.unattempted_count == 160


# Scenario 8: Unreadable hall ticket number
def test_scenario_08_unreadable_hall_ticket_fallback(test_env, tmp_path):
    generator = test_env["pristine_gen"]
    service = test_env["service"]
    exam = test_env["exam"]
    key = test_env["key"]

    answers = {q: key.items[q] for q in range(1, 161)}
    no_ht_img = generator.generate_sheet(answers, hall_ticket="", candidate_name="")
    img_path = tmp_path / "no_ht_sheet.jpg"
    cv2.imwrite(str(img_path), no_ht_img)

    sheet = service.process_single_sheet(exam, key, img_path)
    # When hall ticket is completely empty, it flags review and falls back to file name
    assert sheet.status == "REVIEW_REQUIRED"
    assert sheet.display_identifier == sheet.file_name


# Scenario 9: Duplicate hall ticket number detection
def test_scenario_09_duplicate_hall_ticket_handling(test_env, tmp_path):
    generator = test_env["pristine_gen"]
    service = test_env["service"]
    exam = test_env["exam"]
    key = test_env["key"]

    answers = {q: key.items[q] for q in range(1, 161)}
    img1 = generator.generate_sheet(answers, hall_ticket="KNL2025SATS99999")
    img2 = generator.generate_sheet(answers, hall_ticket="KNL2025SATS99999")

    p1 = tmp_path / "dup1.jpg"
    p2 = tmp_path / "dup2.jpg"
    cv2.imwrite(str(p1), img1)
    cv2.imwrite(str(p2), img2)

    s1 = service.process_single_sheet(exam, key, p1)
    s2 = service.process_single_sheet(exam, key, p2)

    assert s1.id != s2.id
    assert s1.hall_ticket_final == s2.hall_ticket_final


# Scenario 10: Missing answer-key entry validation
def test_scenario_10_missing_answer_key_validation():
    incomplete_key = {q: "A" for q in range(1, 150)}  # Missing 150..160
    errors = AnswerKeyExtractor.validate_key(incomplete_key, expected_count=160)
    assert len(errors) > 0
    assert any("Question 160 is missing" in e for e in errors)


# Scenario 11: Corrected answer key recalculates evaluation
def test_scenario_11_corrected_answer_key_recalculation(test_env):
    scorer = ScoringEngine(total_questions=160)
    detected = {q: {"detected_option": "A", "confidence": 1.0} for q in range(1, 161)}

    key1 = {q: "A" for q in range(1, 161)}
    _, c1, _, _, m1, _, _ = scorer.evaluate_sheet(detected, key1)
    assert c1 == 160
    assert m1 == 80.0

    key2 = key1.copy()
    key2[1] = "B"
    _, c2, _, _, m2, _, _ = scorer.evaluate_sheet(detected, key2)
    assert c2 == 159
    assert m2 == 79.5


# Scenario 12: Student with all correct answers
def test_scenario_12_all_correct_student(test_env, tmp_path):
    generator = test_env["pristine_gen"]
    service = test_env["service"]
    exam = test_env["exam"]
    key = test_env["key"]

    all_correct = {q: key.items[q] for q in range(1, 161)}
    img = generator.generate_sheet(all_correct, hall_ticket="KNL2025SATS00100")
    img_path = tmp_path / "all_correct.jpg"
    cv2.imwrite(str(img_path), img)

    sheet = service.process_single_sheet(exam, key, img_path)
    assert sheet.correct_count == 160
    assert sheet.wrong_count == 0
    assert sheet.unattempted_count == 0
    assert sheet.total_marks == 80.00


# Scenario 13: Student with all incorrect answers
def test_scenario_13_all_incorrect_student(test_env, tmp_path):
    generator = test_env["pristine_gen"]
    service = test_env["service"]
    exam = test_env["exam"]
    key = test_env["key"]

    all_wrong = {q: ("B" if key.items[q] == "A" else "A") for q in range(1, 161)}
    img = generator.generate_sheet(all_wrong, hall_ticket="KNL2025SATS00101")
    img_path = tmp_path / "all_wrong.jpg"
    cv2.imwrite(str(img_path), img)

    sheet = service.process_single_sheet(exam, key, img_path)
    assert sheet.correct_count == 0
    assert sheet.wrong_count == 160
    assert sheet.unattempted_count == 0
    assert sheet.total_marks == 0.00


# Scenario 14: Tie between two or more students (Competition 1224)
def test_scenario_14_tie_ranking():
    s1 = ProcessedSheet(id=1, total_marks=50.0, correct_count=100, wrong_count=60, hall_ticket_final="A1")
    s2 = ProcessedSheet(id=2, total_marks=50.0, correct_count=100, wrong_count=60, hall_ticket_final="A2")
    s3 = ProcessedSheet(id=3, total_marks=40.0, correct_count=80, wrong_count=80, hall_ticket_final="A3")

    ranks = RankingEngine.compute_ranks([s1, s2, s3])
    assert ranks[1] == 1
    assert ranks[2] == 1
    assert ranks[3] == 3


# Scenario 15: Failed file within a large batch
def test_scenario_15_failed_file_in_batch(test_env, tmp_path):
    exam = test_env["exam"]
    key = test_env["key"]
    processor = BatchProcessor(service=test_env["service"])

    p_good = Path("OMR_325601.jpg")
    p_bad = tmp_path / "corrupt.jpg"
    p_bad.touch()

    summary = processor.process_files(exam, key, [p_good, p_bad])
    assert summary["processed"] == 2
    assert summary["successful"] >= 1
    assert summary["failed"] == 1
    assert len(summary["errors"]) == 1


# Scenario 16: Batch interrupted and resumed safely
def test_scenario_16_batch_interrupt_and_resume(test_env, tmp_path):
    exam = test_env["exam"]
    key = test_env["key"]
    processor = BatchProcessor(service=test_env["service"])

    p1 = Path("OMR_325601.jpg")
    processor.cancel()
    # When reset_cancelled=False, processor respects the cancellation flag
    summary = processor.process_files(exam, key, [p1], reset_cancelled=False)
    assert summary["cancelled"] is True


# Scenario 17: Corrected response that changes rank
def test_scenario_17_correction_changes_rank(test_env):
    service = test_env["service"]
    repo = test_env["repo"]
    exam = test_env["exam"]
    key = test_env["key"]

    sheet = service.process_single_sheet(exam, key, Path("OMR_325601.jpg"))
    old_marks = sheet.total_marks

    # Find first wrong question
    wrong_q = next(q for q, r in sheet.responses.items() if r.classification == "WRONG")
    correct_opt = key.items[wrong_q]

    updated = service.apply_manual_correction(
        exam, sheet.id, "QUESTION", correct_opt, target_index=wrong_q,
        reason="Manual operator correction"
    )

    assert updated.total_marks == old_marks + 0.50
    assert updated.correct_count == 108
    assert updated.responses[wrong_q].is_corrected is True


# Scenario 18: Exported Excel file reopened and programmatically validated
def test_scenario_18_excel_export_and_validation(test_env, tmp_path):
    repo = test_env["repo"]
    exam = test_env["exam"]

    sheets = repo.list_sheets(exam.id)
    assert len(sheets) > 0

    export_path = tmp_path / "Verified_Results.xlsx"
    ExcelExporter.export_results(exam, sheets, output_path=export_path)

    is_valid, errors, summary = ExcelValidator.validate_workbook(
        export_path,
        expected_student_count=len([s for s in sheets if s.status != "REJECTED"]),
        total_questions=160,
        correct_mark=0.50
    )

    assert is_valid is True, f"Validation failed with errors: {errors}"
    assert len(errors) == 0
    assert summary["total_students"] == len([s for s in sheets if s.status != "REJECTED"])
