"""Relational repository for persistence and transactional queries."""
import sqlite3
from typing import Optional, List, Dict, Any
from app.database.connection import db_manager, DatabaseManager
from app.models.entities import (
    Examination, AnswerKey, ProcessedSheet, QuestionResult, AuditCorrection
)


class Repository:
    """Provides strongly typed CRUD and query routines."""

    def __init__(self, manager: Optional[DatabaseManager] = None):
        self.manager = manager or db_manager

    # --- Examinations ---
    def create_examination(self, exam: Examination) -> int:
        query = """
            INSERT INTO examinations (code, name, total_questions, correct_mark, wrong_mark,
                                     unattempted_mark, template_name, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self.manager.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, (
                exam.code, exam.name, exam.total_questions, exam.correct_mark,
                exam.wrong_mark, exam.unattempted_mark, exam.template_name,
                exam.status, exam.created_at
            ))
            conn.commit()
            exam.id = cur.lastrowid
            return cur.lastrowid

    def get_examination(self, exam_id: int) -> Optional[Examination]:
        query = "SELECT * FROM examinations WHERE id = ?"
        with self.manager.get_connection() as conn:
            row = conn.execute(query, (exam_id,)).fetchone()
            if not row:
                return None
            return Examination(
                id=row["id"], code=row["code"], name=row["name"],
                total_questions=row["total_questions"], correct_mark=row["correct_mark"],
                wrong_mark=row["wrong_mark"], unattempted_mark=row["unattempted_mark"],
                template_name=row["template_name"], status=row["status"],
                created_at=row["created_at"]
            )

    def get_examination_by_code(self, code: str) -> Optional[Examination]:
        query = "SELECT * FROM examinations WHERE code = ?"
        with self.manager.get_connection() as conn:
            row = conn.execute(query, (code,)).fetchone()
            if not row:
                return None
            return Examination(
                id=row["id"], code=row["code"], name=row["name"],
                total_questions=row["total_questions"], correct_mark=row["correct_mark"],
                wrong_mark=row["wrong_mark"], unattempted_mark=row["unattempted_mark"],
                template_name=row["template_name"], status=row["status"],
                created_at=row["created_at"]
            )

    def list_examinations(self) -> List[Examination]:
        query = "SELECT * FROM examinations ORDER BY id DESC"
        with self.manager.get_connection() as conn:
            rows = conn.execute(query).fetchall()
            return [
                Examination(
                    id=r["id"], code=r["code"], name=r["name"],
                    total_questions=r["total_questions"], correct_mark=r["correct_mark"],
                    wrong_mark=r["wrong_mark"], unattempted_mark=r["unattempted_mark"],
                    template_name=r["template_name"], status=r["status"],
                    created_at=r["created_at"]
                ) for r in rows
            ]

    # --- Answer Keys ---
    def save_answer_key(self, key: AnswerKey) -> int:
        with self.manager.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO answer_keys (id, exam_id, version_number, version_hash, is_locked, source_file, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (key.id, key.exam_id, key.version_number, key.version_hash, 1 if key.is_locked else 0, key.source_file, key.created_at))
            key_id = cur.lastrowid or key.id

            # Save items
            cur.execute("DELETE FROM answer_key_items WHERE answer_key_id = ?", (key_id,))
            for q_num, opt in key.items.items():
                cur.execute("""
                    INSERT INTO answer_key_items (answer_key_id, question_number, correct_option, confidence)
                    VALUES (?, ?, ?, 1.0)
                """, (key_id, q_num, opt))
            conn.commit()
            key.id = key_id
            return key_id

    def get_latest_answer_key(self, exam_id: int) -> Optional[AnswerKey]:
        with self.manager.get_connection() as conn:
            row = conn.execute("""
                SELECT * FROM answer_keys WHERE exam_id = ? ORDER BY version_number DESC LIMIT 1
            """, (exam_id,)).fetchone()
            if not row:
                return None
            key = AnswerKey(
                id=row["id"], exam_id=row["exam_id"], version_number=row["version_number"],
                version_hash=row["version_hash"], is_locked=bool(row["is_locked"]),
                source_file=row["source_file"], created_at=row["created_at"]
            )
            item_rows = conn.execute("""
                SELECT question_number, correct_option FROM answer_key_items WHERE answer_key_id = ?
            """, (key.id,)).fetchall()
            key.items = {r["question_number"]: r["correct_option"] for r in item_rows}
            return key

    def lock_answer_key(self, key_id: int) -> None:
        with self.manager.get_connection() as conn:
            conn.execute("UPDATE answer_keys SET is_locked = 1 WHERE id = ?", (key_id,))
            conn.commit()

    # --- Processed Sheets ---
    def save_processed_sheet(self, sheet: ProcessedSheet) -> int:
        with self.manager.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO processed_sheets
                (id, exam_id, file_path, file_name, file_hash, hall_ticket_ocr, hall_ticket_final,
                 candidate_name_ocr, candidate_name_final, status, review_reason, correct_count,
                 wrong_count, unattempted_count, total_marks, student_rank, skew_angle, processed_at, verified_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sheet.id, sheet.exam_id, sheet.file_path, sheet.file_name, sheet.file_hash,
                sheet.hall_ticket_ocr, sheet.hall_ticket_final, sheet.candidate_name_ocr,
                sheet.candidate_name_final, sheet.status, sheet.review_reason, sheet.correct_count,
                sheet.wrong_count, sheet.unattempted_count, sheet.total_marks, sheet.student_rank,
                sheet.skew_angle, sheet.processed_at, sheet.verified_at
            ))
            sheet_id = cur.lastrowid or sheet.id

            # Save responses if present
            if sheet.responses:
                cur.execute("DELETE FROM question_responses WHERE sheet_id = ?", (sheet_id,))
                for q_num, resp in sheet.responses.items():
                    fills = resp.fills if len(resp.fills) == 4 else [0.0, 0.0, 0.0, 0.0]
                    cur.execute("""
                        INSERT INTO question_responses
                        (sheet_id, question_number, detected_option, correct_option, classification,
                         awarded_marks, confidence, fill_a, fill_b, fill_c, fill_d, is_corrected, corrected_option)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        sheet_id, q_num, resp.detected_option, resp.correct_option,
                        resp.classification, resp.awarded_marks, resp.confidence,
                        fills[0], fills[1], fills[2], fills[3],
                        1 if resp.is_corrected else 0, resp.corrected_option
                    ))
            conn.commit()
            sheet.id = sheet_id
            return sheet_id

    def get_sheet(self, sheet_id: int) -> Optional[ProcessedSheet]:
        with self.manager.get_connection() as conn:
            row = conn.execute("SELECT * FROM processed_sheets WHERE id = ?", (sheet_id,)).fetchone()
            if not row:
                return None
            sheet = self._row_to_sheet(row)
            # Fetch responses
            resp_rows = conn.execute("SELECT * FROM question_responses WHERE sheet_id = ? ORDER BY question_number", (sheet_id,)).fetchall()
            for r in resp_rows:
                sheet.responses[r["question_number"]] = QuestionResult(
                    question_number=r["question_number"],
                    detected_option=r["detected_option"],
                    correct_option=r["correct_option"],
                    classification=r["classification"],
                    awarded_marks=r["awarded_marks"],
                    confidence=r["confidence"],
                    fills=[r["fill_a"] or 0.0, r["fill_b"] or 0.0, r["fill_c"] or 0.0, r["fill_d"] or 0.0],
                    is_corrected=bool(r["is_corrected"]),
                    corrected_option=r["corrected_option"]
                )
            return sheet

    def get_sheet_by_path(self, exam_id: int, file_path: str) -> Optional[ProcessedSheet]:
        with self.manager.get_connection() as conn:
            row = conn.execute("SELECT * FROM processed_sheets WHERE exam_id = ? AND file_path = ?", (exam_id, file_path)).fetchone()
            if not row:
                return None
            return self.get_sheet(row["id"])

    def list_sheets(self, exam_id: int, status: Optional[str] = None) -> List[ProcessedSheet]:
        with self.manager.get_connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM processed_sheets WHERE exam_id = ? AND status = ? ORDER BY student_rank ASC, id ASC",
                    (exam_id, status)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM processed_sheets WHERE exam_id = ? ORDER BY student_rank ASC, id ASC",
                    (exam_id,)
                ).fetchall()
            return [self._row_to_sheet(r) for r in rows]

    def update_ranks(self, exam_id: int, rank_map: Dict[int, int]) -> None:
        """Batch updates student ranks."""
        with self.manager.get_connection() as conn:
            cur = conn.cursor()
            for sheet_id, rank in rank_map.items():
                cur.execute("UPDATE processed_sheets SET student_rank = ? WHERE id = ? AND exam_id = ?", (rank, sheet_id, exam_id))
            conn.commit()

    # --- Audit Corrections ---
    def log_audit(self, correction: AuditCorrection) -> int:
        with self.manager.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO audit_corrections (sheet_id, field_type, target_index, old_value, new_value, reason, operator, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                correction.sheet_id, correction.field_type, correction.target_index,
                correction.old_value, correction.new_value, correction.reason,
                correction.operator, correction.timestamp
            ))
            conn.commit()
            return cur.lastrowid

    def get_audit_history(self, sheet_id: Optional[int] = None) -> List[AuditCorrection]:
        with self.manager.get_connection() as conn:
            if sheet_id:
                rows = conn.execute("SELECT * FROM audit_corrections WHERE sheet_id = ? ORDER BY id DESC", (sheet_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM audit_corrections ORDER BY id DESC").fetchall()
            return [
                AuditCorrection(
                    id=r["id"], sheet_id=r["sheet_id"], field_type=r["field_type"],
                    target_index=r["target_index"], old_value=r["old_value"],
                    new_value=r["new_value"], reason=r["reason"],
                    operator=r["operator"], timestamp=r["timestamp"]
                ) for r in rows
            ]

    # --- Dashboard Metrics ---
    def get_dashboard_stats(self, exam_id: Optional[int] = None) -> Dict[str, Any]:
        with self.manager.get_connection() as conn:
            if exam_id:
                total_sheets = conn.execute("SELECT COUNT(*) FROM processed_sheets WHERE exam_id = ?", (exam_id,)).fetchone()[0]
                success_count = conn.execute("SELECT COUNT(*) FROM processed_sheets WHERE exam_id = ? AND status = 'SUCCESS'", (exam_id,)).fetchone()[0]
                review_count = conn.execute("SELECT COUNT(*) FROM processed_sheets WHERE exam_id = ? AND status = 'REVIEW_REQUIRED'", (exam_id,)).fetchone()[0]
                rejected_count = conn.execute("SELECT COUNT(*) FROM processed_sheets WHERE exam_id = ? AND status = 'REJECTED'", (exam_id,)).fetchone()[0]
                evaluated_count = conn.execute("SELECT COUNT(*) FROM processed_sheets WHERE exam_id = ? AND status IN ('SUCCESS', 'VERIFIED')", (exam_id,)).fetchone()[0]
                export_count = conn.execute("SELECT COUNT(*) FROM export_history WHERE exam_id = ?", (exam_id,)).fetchone()[0]
            else:
                total_exams = conn.execute("SELECT COUNT(*) FROM examinations").fetchone()[0]
                total_sheets = conn.execute("SELECT COUNT(*) FROM processed_sheets").fetchone()[0]
                success_count = conn.execute("SELECT COUNT(*) FROM processed_sheets WHERE status = 'SUCCESS'").fetchone()[0]
                review_count = conn.execute("SELECT COUNT(*) FROM processed_sheets WHERE status = 'REVIEW_REQUIRED'").fetchone()[0]
                rejected_count = conn.execute("SELECT COUNT(*) FROM processed_sheets WHERE status = 'REJECTED'").fetchone()[0]
                evaluated_count = conn.execute("SELECT COUNT(*) FROM processed_sheets WHERE status IN ('SUCCESS', 'VERIFIED')").fetchone()[0]
                export_count = conn.execute("SELECT COUNT(*) FROM export_history").fetchone()[0]
                return {
                    "total_examinations": total_exams,
                    "total_sheets": total_sheets,
                    "success_count": success_count,
                    "review_count": review_count,
                    "rejected_count": rejected_count,
                    "evaluated_count": evaluated_count,
                    "export_count": export_count
                }

            return {
                "total_sheets": total_sheets,
                "success_count": success_count,
                "review_count": review_count,
                "rejected_count": rejected_count,
                "evaluated_count": evaluated_count,
                "export_count": export_count
            }

    def _row_to_sheet(self, row: sqlite3.Row) -> ProcessedSheet:
        return ProcessedSheet(
            id=row["id"], exam_id=row["exam_id"], file_path=row["file_path"],
            file_name=row["file_name"], file_hash=row["file_hash"],
            hall_ticket_ocr=row["hall_ticket_ocr"] or "",
            hall_ticket_final=row["hall_ticket_final"] or "",
            candidate_name_ocr=row["candidate_name_ocr"] or "",
            candidate_name_final=row["candidate_name_final"] or "",
            status=row["status"], review_reason=row["review_reason"] or "",
            correct_count=row["correct_count"], wrong_count=row["wrong_count"],
            unattempted_count=row["unattempted_count"], total_marks=row["total_marks"],
            student_rank=row["student_rank"], skew_angle=row["skew_angle"] or 0.0,
            processed_at=row["processed_at"], verified_at=row["verified_at"]
        )


# Global default repository
repository = Repository()

