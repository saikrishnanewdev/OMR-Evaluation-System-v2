"""Batch processing queue and thread management for multiple OMR sheets."""
import traceback
from pathlib import Path
from typing import List, Callable, Optional, Dict, Any
from app.models.entities import Examination, AnswerKey, ProcessedSheet
from app.services.evaluation_service import EvaluationService, evaluation_service


class BatchProcessor:
    """Processes folders and lists of scanned sheets with visible progress and graceful cancellation."""

    def __init__(self, service: Optional[EvaluationService] = None):
        self.service = service or evaluation_service
        self._is_cancelled = False
        self._is_paused = False

    def cancel(self) -> None:
        """Flags the batch processor to stop after the current file."""
        self._is_cancelled = True

    def process_files(
        self,
        exam: Examination,
        answer_key: AnswerKey,
        file_paths: List[Path],
        progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
        reset_cancelled: bool = True
    ) -> Dict[str, Any]:
        """
        Executes evaluation over a batch of file paths.
        progress_callback signature: (current_idx, total_count, current_filename, status_str)
        """
        if reset_cancelled:
            self._is_cancelled = False
        total = len(file_paths)
        successful = 0
        review_required = 0
        failed = 0
        errors: List[Dict[str, str]] = []

        for idx, path in enumerate(file_paths, start=1):
            if self._is_cancelled:
                break

            filename = path.name
            try:
                sheet = self.service.process_single_sheet(exam, answer_key, path)
                if sheet.status == "SUCCESS":
                    successful += 1
                    status_text = "SUCCESS"
                elif sheet.status == "REVIEW_REQUIRED":
                    review_required += 1
                    status_text = "REVIEW_REQUIRED"
                else:
                    failed += 1
                    status_text = sheet.status

                if progress_callback:
                    progress_callback(idx, total, filename, status_text)

            except Exception as e:
                failed += 1
                err_msg = str(e)
                errors.append({"file": filename, "error": err_msg, "trace": traceback.format_exc()})
                if progress_callback:
                    progress_callback(idx, total, filename, f"ERROR: {err_msg}")

        # Recalculate ranks across examination upon completion
        self.service.recalculate_exam_ranks(exam.id)

        return {
            "total": total,
            "processed": successful + review_required + failed,
            "successful": successful,
            "review_required": review_required,
            "failed": failed,
            "errors": errors,
            "cancelled": self._is_cancelled
        }
