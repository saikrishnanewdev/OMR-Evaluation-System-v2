"""Automated test suite for dynamic scoring and question ranges.

There are no fixed layouts any more: the question count comes from
the answer-key PDF and the bubbles are found on the sheet itself, so
the old 160Q/200Q template geometry and fixed-identity tests are
gone. Scoring itself is unchanged (see test_centre_sampling.py for
the dynamic 160Q benchmark: 107 correct on the sample sheet).
"""
import pytest
from pathlib import Path
from decimal import Decimal
from app.evaluation.scoring_engine import ScoringEngine
from app.evaluation.answer_key import AnswerKeyExtractor


def test_dynamic_scoring_two_questions_one_mark():
    """Requirement 1A: 2 questions has 1 mark (0.50 marks per question)."""
    engine = ScoringEngine(correct_mark=0.50, wrong_mark=0.00, unattempted_mark=0.00, total_questions=160)
    
    mock_detected = {q: {"detected_option": "A", "confidence": 0.9, "fills": [100, 10, 10, 10]} for q in range(1, 161)}
    mock_key = {q: "A" for q in range(1, 161)}

    _, corr, wr, un, marks, _, _ = engine.evaluate_sheet(mock_detected, mock_key)
    assert corr == 160
    assert wr == 0
    assert un == 0
    assert marks == 80.00  # 160 * 0.50 = 80.00


def test_dynamic_scoring_one_question_one_mark():
    """Requirement 1B: 1 question has 1 mark (1.00 mark per question)."""
    engine = ScoringEngine(correct_mark=1.00, wrong_mark=0.00, unattempted_mark=0.00, total_questions=200)
    
    mock_detected = {q: {"detected_option": "B", "confidence": 0.9, "fills": [10, 100, 10, 10]} for q in range(1, 201)}
    mock_key = {q: "B" for q in range(1, 201)}

    _, corr, wr, un, marks, _, _ = engine.evaluate_sheet(mock_detected, mock_key)
    assert corr == 200
    assert marks == 200.00


def test_dynamic_scoring_negative_marking():
    """Requirement 1C: Negative marking (e.g. -0.33 per wrong answer)."""
    engine = ScoringEngine(correct_mark=1.00, wrong_mark=-0.33, unattempted_mark=0.00, total_questions=100)
    
    # 70 correct, 20 wrong, 10 unattempted
    mock_detected = {}
    mock_key = {q: "A" for q in range(1, 101)}
    for q in range(1, 71):
        mock_detected[q] = {"detected_option": "A"}
    for q in range(71, 91):
        mock_detected[q] = {"detected_option": "B"}
    for q in range(91, 101):
        mock_detected[q] = {"detected_option": "BLANK"}

    _, corr, wr, un, marks, _, _ = engine.evaluate_sheet(mock_detected, mock_key)
    assert corr == 70
    assert wr == 20
    assert un == 10
    # Expected marks: 70 * 1.00 - 20 * 0.33 = 70.00 - 6.60 = 63.40
    assert marks == 63.40


def test_evaluation_scope_from_to_row():
    """Test evaluation restricted from row 1 to row 150 (ignoring rows 151..200)."""
    engine = ScoringEngine(
        correct_mark=1.00, wrong_mark=-0.25, unattempted_mark=0.00,
        total_questions=200, from_question=1, to_question=150
    )
    
    mock_detected = {q: {"detected_option": "A"} for q in range(1, 201)}
    mock_key = {q: "A" for q in range(1, 201)}

    responses, corr, wr, un, marks, _, _ = engine.evaluate_sheet(mock_detected, mock_key)
    assert corr == 150
    assert wr == 0
    assert un == 0
    assert marks == 150.00

    # Questions 151..200 must be marked as EXCLUDED with 0 marks
    for q in range(151, 201):
        assert responses[q].classification == "EXCLUDED"
        assert responses[q].awarded_marks == 0.0


def test_parse_200q_pdf_key_if_present():
    """Test AnswerKeyExtractor on real 200Q PDF key."""
    key_path = Path(r"c:\Projects\PC\Syam\AMP KTS-91\91 KEY.pdf")
    if not key_path.exists():
        pytest.skip("Test file 91 KEY.pdf not found.")

    extractor = AnswerKeyExtractor()
    key_obj = extractor.extract_from_pdf(key_path)
    assert len(key_obj.items) == 200
    assert key_obj.items[1] == "B"
    assert key_obj.items[2] == "A"
    assert key_obj.items[200] == "B"
