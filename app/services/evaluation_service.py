"""High-level evaluation orchestration service connecting OMR, OCR, scoring, and persistence."""
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from app.models.entities import (
    Examination, AnswerKey, ProcessedSheet, QuestionResult, AuditCorrection
)
from app.omr.preprocessor import Preprocessor
from app.ocr.engine import OCREngine, ocr_engine
from app.evaluation.scoring_engine import ScoringEngine
from app.evaluation.ranking_engine import RankingEngine
from app.database.repository import Repository, repository


class EvaluationService:
    """Orchestrates image loading, vision pipelines, OCR, deterministic scoring, and persistence."""

    def __init__(
        self,
        repo: Optional[Repository] = None,
        ocr: Optional[OCREngine] = None
    ):
        self.repo = repo or repository
        self.ocr = ocr or ocr_engine

    def process_single_sheet(
        self,
        exam: Examination,
        answer_key: AnswerKey,
        file_path: Path
    ) -> ProcessedSheet:
        """
        Processes a single OMR sheet from raw image file to scored and persisted record.

        Everything is read dynamically from the sheet itself: the
        hall-ticket and name rows are found from the printed labels,
        and the answer bubbles are found from the pink answer columns
        below ANSWERS. There is no fixed template. A sheet on which
        dynamic detection finds no answer columns and no identity is
        rejected as not an OMR answer sheet.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Compute file hash to detect exact duplicates
        with open(file_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # Check if already processed
        existing = self.repo.get_sheet_by_path(exam.id, str(file_path))
        if existing and existing.status in ("SUCCESS", "VERIFIED"):
            return existing

        def _rejected(reason: str, skew: float = 0.0) -> ProcessedSheet:
            sheet = ProcessedSheet(
                id=existing.id if existing else None,
                exam_id=exam.id,
                file_path=str(file_path),
                file_name=file_path.name,
                file_hash=file_hash,
                hall_ticket_ocr="",
                hall_ticket_final="",
                candidate_name_ocr="",
                candidate_name_final="",
                status="REJECTED",
                review_reason=reason,
                correct_count=0,
                wrong_count=0,
                unattempted_count=0,
                total_marks=0.0,
                student_rank=0,
                skew_angle=skew,
                responses={}
            )
            self.repo.save_processed_sheet(sheet)
            return sheet

        # 1. Load image & preprocess (straighten the page via the
        # timing marks). If the page cannot be straightened at all,
        # it is not a scannable sheet.
        raw_bgr = Preprocessor.load_image(file_path)
        try:
            aligned_bgr, skew_angle = Preprocessor.align_and_deskew(raw_bgr)
        except Exception:
            return _rejected("Not an OMR answer sheet (page could not be aligned).")

        # Dynamic detection normally runs on the warped `aligned_bgr`.
        # But the warp can cut the top of the page off when the timing
        # track is only partially detected — on the 200Q Syam sheet
        # the first detected mark sat far below the real top of the
        # track, so the hall-ticket row mapped to y < 0 and identity
        # came back blank. A box row touching the top edge is the
        # tell-tale sign of that cut-off. In that case dynamic runs
        # on a deskewed-only copy of the raw scan instead (see
        # Preprocessor.deskew_only), where the whole page stays in
        # frame. Sheets with no timing track at all (the 20Q strip
        # and the 50Q photo) also read from the deskewed-only copy:
        # the warp to the reference points would distort them.
        try:
            deskewed_bgr, _ = Preprocessor.deskew_only(raw_bgr)
        except Exception:
            deskewed_bgr = aligned_bgr
        dyn_image = aligned_bgr
        try:
            from app.omr.dynamic import top_is_cut_off
            left_m, right_m, _ = Preprocessor.detect_timing_tracks(raw_bgr)
            no_track = len(left_m) < 2 and len(right_m) < 2
            if top_is_cut_off(aligned_bgr) or no_track:
                dyn_image = deskewed_bgr
        except Exception:
            pass

        # The key PDF only tells us how many questions to expect:
        # its item count is the question count, nothing about layout.
        expected_q = None
        try:
            if answer_key is not None and answer_key.items:
                expected_q = len(answer_key.items)
        except Exception:
            expected_q = None
        if not expected_q:
            expected_q = exam.total_questions if (exam and exam.total_questions) else 160

        # 2. Dynamic detection — no layout, no fixed coordinates.
        #    Find the label, read the boxes on the same line; find the
        #    question number, read the 4 circles on the same line.
        prefix = exam.code.strip() if (exam and exam.code and exam.code.strip()) else None
        detected_results = None
        ht_text = name_text = ""
        ocr_conf = 0.0
        ht_valid = False
        try:
            from app.omr.dynamic import (
                analyze_sheet_dynamic, dynamic_rows_to_detected)
            dyn = analyze_sheet_dynamic(
                dyn_image, expected_questions=expected_q,
                ocr_engine=self.ocr, exam_prefix=prefix)
            if dyn.method == "dynamic" and dyn.found_questions >= 1:
                detected_results = dynamic_rows_to_detected(dyn)
                if dyn.identity.hall_ticket or dyn.identity.name:
                    import re as _re
                    _ht = dyn.identity.hall_ticket or ""
                    _nm = dyn.identity.name or ""
                    # Only trust dynamic identity if it looks like a
                    # real hall ticket / name.
                    if _ht and not _re.match(r"^[A-Z0-9]{4,20}$", _ht):
                        _ht = ""
                    if _nm and len(_nm) < 3:
                        _nm = ""
                    ht_text, name_text = _ht, _nm
                    ocr_conf = dyn.identity.confidence
                    ht_valid = bool(_ht)
        except Exception:
            detected_results = None

        if detected_results is None and not ht_text and not name_text:
            # Dynamic found no answer columns and no identity: this
            # is not an OMR answer sheet. (There is no fixed-template
            # fallback any more — a sheet dynamic cannot read is
            # rejected, not guessed at.)
            return _rejected(
                "Not an OMR answer sheet (no answer columns found).",
                skew=round(skew_angle, 2))
        if detected_results is None:
            # Identity found but no bubbles: score every question
            # as unattempted.
            detected_results = {}

        ht_conf = ocr_conf
        name_conf = ocr_conf

        # 3. Deterministic Scoring
        scorer = ScoringEngine(
            correct_mark=exam.correct_mark,
            wrong_mark=exam.wrong_mark,
            unattempted_mark=exam.unattempted_mark,
            total_questions=exam.total_questions
        )
        (
            responses, correct_cnt, wrong_cnt, unattempted_cnt,
            total_score, status, review_reason
        ) = scorer.evaluate_sheet(detected_results, answer_key.items)

        # Check for student identification review flags
        if not ht_text and not name_text:
            status = "REVIEW_REQUIRED"
            review_reason = (review_reason + " Unreadable identification fields.").strip()

        sheet = ProcessedSheet(
            id=existing.id if existing else None,
            exam_id=exam.id,
            file_path=str(file_path),
            file_name=file_path.name,
            file_hash=file_hash,
            hall_ticket_ocr=ht_text,
            hall_ticket_final=ht_text,
            candidate_name_ocr=name_text,
            candidate_name_final=name_text,
            status=status,
            review_reason=review_reason,
            correct_count=correct_cnt,
            wrong_count=wrong_cnt,
            unattempted_count=unattempted_cnt,
            total_marks=total_score,
            student_rank=0,  # Will be ranked across batch
            skew_angle=round(skew_angle, 2),
            responses=responses
        )

        sheet_id = self.repo.save_processed_sheet(sheet)
        sheet.id = sheet_id
        return sheet

    def recalculate_exam_ranks(self, exam_id: int) -> None:
        """
        Recalculates competition ranks (1224) across all evaluated sheets for an examination.
        """
        sheets = self.repo.list_sheets(exam_id)
        if not sheets:
            return

        rank_map = RankingEngine.compute_ranks(sheets)
        self.repo.update_ranks(exam_id, rank_map)

    def apply_manual_correction(
        self,
        exam: Examination,
        sheet_id: int,
        field_type: str,
        new_value: str,
        target_index: Optional[int] = None,
        reason: str = "Manual operator review",
        operator: str = "Operator"
    ) -> ProcessedSheet:
        """
        Applies and audits an operator correction to candidate info or bubble answer.
        Recalculates scores and batch ranks immediately.
        """
        sheet = self.repo.get_sheet(sheet_id)
        if not sheet:
            raise ValueError(f"Sheet with ID {sheet_id} not found.")

        old_val = ""
        if field_type == "HALL_TICKET":
            old_val = sheet.hall_ticket_final
            sheet.hall_ticket_final = new_value.strip().upper()
        elif field_type == "CANDIDATE_NAME":
            old_val = sheet.candidate_name_final
            sheet.candidate_name_final = new_value.strip().upper()
        elif field_type == "QUESTION":
            if target_index is None or target_index not in sheet.responses:
                raise ValueError(f"Invalid question index for correction: {target_index}")
            resp = sheet.responses[target_index]
            old_val = resp.detected_option
            resp.detected_option = new_value.strip().upper()
            resp.is_corrected = True
            resp.corrected_option = new_value.strip().upper()

            # Recalculate responses
            key = self.repo.get_latest_answer_key(exam.id)
            if key:
                scorer = ScoringEngine(
                    correct_mark=exam.correct_mark,
                    wrong_mark=exam.wrong_mark,
                    unattempted_mark=exam.unattempted_mark,
                    total_questions=exam.total_questions
                )
                detected_dict = {
                    q: {"detected_option": r.detected_option, "confidence": r.confidence, "fills": r.fills}
                    for q, r in sheet.responses.items()
                }
                (
                    new_responses, correct_cnt, wrong_cnt, unattempted_cnt,
                    total_score, status, rev_reason
                ) = scorer.evaluate_sheet(detected_dict, key.items)

                # Preserve correction flags
                new_responses[target_index].is_corrected = True
                new_responses[target_index].corrected_option = new_value.strip().upper()

                sheet.responses = new_responses
                sheet.correct_count = correct_cnt
                sheet.wrong_count = wrong_cnt
                sheet.unattempted_count = unattempted_cnt
                sheet.total_marks = total_score
                sheet.status = "VERIFIED"

        # Save audit record
        audit = AuditCorrection(
            sheet_id=sheet_id,
            field_type=field_type,
            target_index=target_index,
            old_value=old_val,
            new_value=new_value,
            reason=reason,
            operator=operator
        )
        self.repo.log_audit(audit)

        # Update sheet in database
        self.repo.save_processed_sheet(sheet)

        # Recalculate ranks across examination
        self.recalculate_exam_ranks(exam.id)

        return self.repo.get_sheet(sheet_id)


# Global evaluation service instance
evaluation_service = EvaluationService()
