"""Automated test suite for dynamic scoring, question ranges, and 200Q physical bubble grid template."""
import pytest
from pathlib import Path
from decimal import Decimal
from app.config.constants import TOTAL_QUESTIONS, TOTAL_QUESTIONS_200
from app.omr.template import get_template, template_160, template_200
from app.evaluation.scoring_engine import ScoringEngine
from app.evaluation.answer_key import AnswerKeyExtractor


def test_templates_dimensions_and_properties():
    """Verify 160Q and 200Q template geometries."""
    t160 = get_template(160)
    assert t160.total_questions == 160
    assert t160.num_columns == 4
    assert t160.questions_per_column == 40
    assert len(t160.column_base_x) == 4

    t200 = get_template(200)
    assert t200.total_questions == 200
    assert t200.num_columns == 5
    assert t200.questions_per_column == 40
    assert len(t200.column_base_x) == 5

    # Verify bubble center bounds
    for q in (1, 40, 41, 80, 81, 120, 121, 160):
        x, y = t160.get_bubble_center(q, 0)
        assert 200 <= x <= 1500
        assert 1000 <= y <= 2250

    for q in (1, 40, 80, 120, 160, 200):
        x, y = t200.get_bubble_center(q, 0)
        assert 200 <= x <= 1500
        assert 1000 <= y <= 2280


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


def test_200q_identity_and_roster_reconciliation():
    """Verify 200Q 17-box HT and 24-box Candidate Name ICR with bottom roster records."""
    import cv2
    from app.ocr.engine import OCREngine
    from app.omr.preprocessor import Preprocessor

    img_path = Path(r"C:\Projects\PC\Syam\FeedBack\TESTING\OMR_343526.jpg")
    if not img_path.exists():
        pytest.skip("Test file OMR_343526.jpg not found.")

    engine = OCREngine()
    im = cv2.imread(str(img_path))
    aligned, _ = Preprocessor.align_and_deskew(im)

    roster = [
        {"roll": "KKD2025KTS00173", "name": ""},
        {"roll": "KK2025KTS01123", "name": "KHYMA BHAVANI"},
        {"roll": "KKD2025KTS00011", "name": "DESA MADHURIMA"},
        {"roll": "RJY2025KTS02115", "name": "G AADHVIKA"},
    ]

    ht, name, conf, valid = engine.extract_identity(
        aligned, exam_prefix="KKD2025KTS", roster=roster, is_200q=True
    )
    assert ht == "KK2025KTS01123"
    assert name == "KHYMA BHAVANI"
    assert valid is True


def test_200q_crossed_7_and_name_dual_signal():
    """Verify 200Q crossed-7 mapping and dual-signal name disambiguation (OMR_348819 -> KKD2025KTS01627)."""
    import cv2
    from app.ocr.engine import OCREngine
    from app.omr.preprocessor import Preprocessor

    img_path = Path(r"C:\Projects\PC\Syam\FeedBack\AP TESTING 05_11\AP TESTING 05\OMR_348819.jpg")
    if not img_path.exists():
        pytest.skip("Test file OMR_348819.jpg not found.")

    engine = OCREngine()
    im = cv2.imread(str(img_path))
    aligned, _ = Preprocessor.align_and_deskew(im)

    roster = [
        {"roll": "KKD2025KTS00062", "name": "KUMMAGIRI HARI BABU"},
        {"roll": "KKD2025KTS01627", "name": "CH ANIL KUMAR"},
        {"roll": "KKD2025KTS03027", "name": ""},
    ]

    ht, name, conf, valid = engine.extract_identity(
        aligned, exam_prefix="KKD2025KTS", roster=roster, is_200q=True
    )
    assert ht == "KKD2025KTS01627"
    assert name == "CH ANIL KUMAR"
    assert valid is True


def test_200q_bilateral_timing_marks_fallback_and_recovery():
    """Verify that single-track timing marks safely fall back to standard grid, preventing vertical column drift."""
    t200 = get_template(200)

    # Mock left tracks (56 marks) and incomplete right tracks (51 marks)
    mock_left = [(100, 400 + i * 28, 20, 10) for i in range(56)]
    mock_right = [(1500, 400 + i * 28, 20, 10) for i in range(51)]

    # Single-sided tracks must NOT trigger track projection; must match standard calibrated grid
    x_single, y_single = t200.get_bubble_center(1, 0, timing_marks_left=mock_left, timing_marks_right=mock_right)
    x_std, y_std = t200.get_bubble_center(1, 0, timing_marks_left=None, timing_marks_right=None)
    assert x_single == x_std
    assert y_single == y_std

    # Real sheet OMR_348820.jpg verification (recovered 33 marks)
    img_path = Path(r"C:\Projects\PC\Syam\FeedBack\AP TESTING 05_11\AP TESTING 05\OMR_348820.jpg")
    key_path = Path(r"C:\Projects\PC\Syam\FeedBack\AP TESTING 05_11\AP TESTING 05\AP CONSTABLE (Prelims cum Mains) ‘Khaki’ MODEL TEST-107.pdf")
    if not (img_path.exists() and key_path.exists()):
        pytest.skip("Test files for 348820 not found.")

    import cv2
    from app.omr.preprocessor import Preprocessor
    from app.omr.bubble_detector import BubbleDetector

    im = cv2.imread(str(img_path))
    aligned, _ = Preprocessor.align_and_deskew(im)
    ink_map = Preprocessor.extract_ink_channel(aligned)
    l_raw, r_raw, _ = Preprocessor.detect_timing_tracks(im)
    key = AnswerKeyExtractor().extract_from_pdf(key_path)

    det = BubbleDetector(t200).analyze_sheet(ink_map, timing_marks=(l_raw, r_raw))
    correct_cnt = sum(1 for q, d in det.items() if d.get("detected_option") == key.items.get(q))
    assert correct_cnt == 33



