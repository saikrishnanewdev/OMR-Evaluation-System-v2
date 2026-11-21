"""Deterministic scoring arithmetic and question response evaluation."""
from typing import Dict, Tuple, List, Optional
from decimal import Decimal, ROUND_HALF_UP
from app.models.entities import QuestionResult, ProcessedSheet
from app.config.constants import (
    TOTAL_QUESTIONS, DEFAULT_CORRECT_MARK,
    DEFAULT_WRONG_MARK, DEFAULT_UNATTEMPTED_MARK
)


class ScoringEngine:
    """Evaluates question responses against an approved answer key with exact arithmetic."""

    def __init__(
        self,
        correct_mark: float = DEFAULT_CORRECT_MARK,
        wrong_mark: float = DEFAULT_WRONG_MARK,
        unattempted_mark: float = DEFAULT_UNATTEMPTED_MARK,
        total_questions: int = TOTAL_QUESTIONS,
        from_question: int = 1,
        to_question: Optional[int] = None
    ):
        self.correct_mark = correct_mark
        self.wrong_mark = wrong_mark
        self.unattempted_mark = unattempted_mark
        self.total_questions = total_questions
        self.from_question = from_question
        self.to_question = to_question if to_question is not None else total_questions

    def evaluate_sheet(
        self,
        detected_results: Dict[int, Dict],
        answer_key: Dict[int, str]
    ) -> Tuple[Dict[int, QuestionResult], int, int, int, float, str, str]:
        """
        Evaluates detected responses against the answer key.
        Supports question ranges (e.g. Q1 to Q150) and dynamic marking schemes (including negative marks).
        Returns:
            (responses_dict, correct_count, wrong_count, unattempted_count,
             total_marks, status, review_reason)
        """
        responses = {}
        correct_count = 0
        wrong_count = 0
        unattempted_count = 0
        ambiguous_count = 0

        # Exact decimal representation to avoid float drift (e.g. 0.50, -0.33)
        dec_correct = Decimal(str(self.correct_mark))
        dec_wrong = Decimal(str(self.wrong_mark))
        dec_unattempted = Decimal(str(self.unattempted_mark))

        total_score_dec = Decimal("0.00")

        from_q = max(1, self.from_question)
        to_q = min(self.total_questions, self.to_question) if self.to_question else self.total_questions

        for q_num in range(1, self.total_questions + 1):
            q_data = detected_results.get(q_num, {})
            det = q_data.get("detected_option", "BLANK")
            conf = q_data.get("confidence", 0.0)
            fills = q_data.get("fills", [0.0, 0.0, 0.0, 0.0])
            correct_ans = answer_key.get(q_num, "")

            # If question is outside evaluation scope, mark as EXCLUDED / 0 marks
            if q_num < from_q or q_num > to_q:
                classification = "EXCLUDED"
                marks = Decimal("0.00")
            elif det == "BLANK":
                classification = "UNATTEMPTED"
                marks = dec_unattempted
                unattempted_count += 1
            elif det == "MULTI":
                classification = "MULTI"
                marks = dec_wrong
                wrong_count += 1
                ambiguous_count += 1
            elif det == "AMBIGUOUS":
                classification = "AMBIGUOUS"
                marks = dec_wrong
                wrong_count += 1
                ambiguous_count += 1
            elif det == correct_ans:
                classification = "CORRECT"
                marks = dec_correct
                correct_count += 1
            else:
                classification = "WRONG"
                marks = dec_wrong
                wrong_count += 1

            total_score_dec += marks

            responses[q_num] = QuestionResult(
                question_number=q_num,
                detected_option=det,
                correct_option=correct_ans,
                classification=classification,
                awarded_marks=float(marks),
                confidence=conf,
                fills=fills,
                is_corrected=False,
                corrected_option=None
            )

        # Mathematical reconciliation check for evaluated range
        num_evaluated = max(0, to_q - from_q + 1)
        reconciled_sum = correct_count + wrong_count + unattempted_count
        if reconciled_sum != num_evaluated:
            raise ValueError(
                f"Arithmetic reconciliation failed: {correct_count} + {wrong_count} + {unattempted_count} = {reconciled_sum} != {num_evaluated}"
            )

        total_marks = float(total_score_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        if ambiguous_count > 0:
            status = "REVIEW_REQUIRED"
            review_reason = f"{ambiguous_count} ambiguous or multi-marked responses detected."
        else:
            status = "SUCCESS"
            review_reason = ""

        return (
            responses, correct_count, wrong_count, unattempted_count,
            total_marks, status, review_reason
        )

