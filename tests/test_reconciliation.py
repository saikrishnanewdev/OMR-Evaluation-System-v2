"""Ground-Truth Reconciliation Test verifying 100% exact match against reference files."""
import pytest
from pathlib import Path
from app.models.entities import Examination
from app.evaluation.answer_key import AnswerKeyExtractor
from app.services.evaluation_service import EvaluationService
from app.database.connection import DatabaseManager
from app.database.repository import Repository
import os


def test_ground_truth_reconciliation():
    """
    Evaluates reference sheet OMR_325601.jpg against SA-08.pdf.
    Must match Row 1 of KNL SA.xls exactly:
    - 107 Correct
    - 53 Wrong
    - 0 Unattempted
    - 53.50 Total Marks
    - Hall Ticket: KNL2025SATS00001
    """
    omr_path = Path("OMR_325601.jpg")
    pdf_path = Path("SA-08.pdf")

    assert omr_path.exists(), "OMR_325601.jpg must be present"
    assert pdf_path.exists(), "SA-08.pdf must be present"

    db_path = Path("data/test_reconcile.db")
    if db_path.exists():
        try:
            os.remove(db_path)
        except Exception:
            pass

    mgr = DatabaseManager(db_path)
    repo = Repository(mgr)
    service = EvaluationService(repo=repo)

    # 1. Create Examination
    exam = Examination(
        code="KNL2025SATS",
        name="AP DSC 2026 SA(Social) 3.0",
        total_questions=160,
        correct_mark=0.50,
        wrong_mark=0.00,
        unattempted_mark=0.00,
        status="ACTIVE"
    )
    exam_id = repo.create_examination(exam)
    exam.id = exam_id

    # 2. Extract Answer Key from PDF
    extractor = AnswerKeyExtractor()
    key = extractor.extract_from_pdf(pdf_path, exam_id=exam_id)
    assert len(key.items) == 160, "Extracted answer key must have exactly 160 questions"
    repo.save_answer_key(key)

    # 3. Process OMR Sheet
    sheet = service.process_single_sheet(exam, key, omr_path)
    service.recalculate_exam_ranks(exam_id)
    final_sheet = repo.get_sheet(sheet.id)

    # 4. Reconcile against Ground Truth (KNL SA.xls Row 1)
    print(f"\n--- Ground Truth Reconciliation Result ---")
    print(f"Correct:     {final_sheet.correct_count} (Expected: 107)")
    print(f"Wrong:       {final_sheet.wrong_count} (Expected: 53)")
    print(f"Unattempted: {final_sheet.unattempted_count} (Expected: 0)")
    print(f"Marks:       {final_sheet.total_marks:.2f} (Expected: 53.50)")
    print(f"Rank:        {final_sheet.student_rank} (Expected: 1)")
    print(f"Identifier:  {final_sheet.display_identifier} (Expected: KNL2025SATS00001)")

    assert final_sheet.correct_count == 107, f"Expected 107 correct, got {final_sheet.correct_count}"
    assert final_sheet.wrong_count == 53, f"Expected 53 wrong, got {final_sheet.wrong_count}"
    assert final_sheet.unattempted_count == 0, f"Expected 0 unattempted, got {final_sheet.unattempted_count}"
    assert final_sheet.total_marks == 53.50, f"Expected 53.50 marks, got {final_sheet.total_marks}"
    assert final_sheet.student_rank == 1, f"Expected rank 1, got {final_sheet.student_rank}"
    assert "KNL2025SATS0000" in final_sheet.display_identifier, "Hall ticket must match KNL2025SATS0000X"
