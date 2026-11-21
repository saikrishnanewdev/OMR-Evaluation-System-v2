"""Automated programmatic verification of generated Excel examination workbooks."""
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional
import openpyxl
from decimal import Decimal
from app.export.excel_exporter import ExcelExporter
from app.config.constants import TOTAL_QUESTIONS


class ExcelValidator:
    """Verifies that an exported Excel workbook strictly complies with examination integrity rules."""

    @classmethod
    def validate_workbook(
        cls,
        file_path: Path,
        expected_student_count: Optional[int] = None,
        total_questions: int = TOTAL_QUESTIONS,
        correct_mark: float = 0.50
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Reopens and inspects an exported Excel workbook.
        Returns: (is_valid: bool, errors: List[str], summary: Dict[str, Any])
        """
        file_path = Path(file_path)
        errors = []

        if not file_path.exists():
            return False, [f"Exported Excel file does not exist: {file_path}"], {}

        try:
            wb = openpyxl.load_workbook(str(file_path), data_only=True)
        except Exception as e:
            return False, [f"Failed to open workbook as valid Excel file: {e}"], {}

        if "Examination Results" not in wb.sheetnames:
            errors.append("Required worksheet 'Examination Results' is missing from workbook.")
            wb.close()
            return False, errors, {}

        ws = wb["Examination Results"]

        # 1. Header Validation
        actual_headers = [ws.cell(row=1, column=c).value for c in range(1, len(ExcelExporter.COLUMNS) + 1)]
        if actual_headers != ExcelExporter.COLUMNS:
            errors.append(f"Header mismatch. Expected: {ExcelExporter.COLUMNS}, Found: {actual_headers}")

        # 2. Data Rows Validation
        data_rows = []
        prev_rank = 0
        dec_correct_factor = Decimal(str(correct_mark))

        for row_idx in range(2, ws.max_row + 1):
            file_val = ws.cell(row=row_idx, column=1).value
            id_val = ws.cell(row=row_idx, column=2).value
            correct_val = ws.cell(row=row_idx, column=3).value
            marks_val = ws.cell(row=row_idx, column=4).value
            wrong_val = ws.cell(row=row_idx, column=5).value
            unattempted_val = ws.cell(row=row_idx, column=6).value
            rank_val = ws.cell(row=row_idx, column=7).value

            # Skip trailing empty rows if any
            if file_val is None and id_val is None:
                continue

            # Check for missing values
            if not file_val:
                errors.append(f"Row {row_idx}: 'File' column is blank.")
            if not id_val:
                errors.append(f"Row {row_idx}: 'Hall Ticket Number/Name' column is blank.")

            # Validate numeric counts
            try:
                c_num = int(correct_val or 0)
                w_num = int(wrong_val or 0)
                u_num = int(unattempted_val or 0)
                m_num = Decimal(str(marks_val or 0.0))
                r_num = int(rank_val or 0)
            except (ValueError, TypeError) as num_err:
                errors.append(f"Row {row_idx}: Non-numeric score or rank values: {num_err}")
                continue

            # Arithmetic check: Correct + Wrong + Unattempted = 160
            row_sum = c_num + w_num + u_num
            if row_sum != total_questions:
                errors.append(
                    f"Row {row_idx} ({id_val}): Question sum mismatch: {c_num} + {w_num} + {u_num} = {row_sum} != {total_questions}"
                )

            # Score check: Correct Marks = Correct * 0.50
            expected_marks = (Decimal(str(c_num)) * dec_correct_factor).quantize(Decimal("0.01"))
            if abs(m_num - expected_marks) > Decimal("0.001"):
                errors.append(
                    f"Row {row_idx} ({id_val}): Score mismatch. Marks={m_num}, Expected={expected_marks}"
                )

            # Rank monotonicity check
            if r_num < prev_rank:
                errors.append(
                    f"Row {row_idx} ({id_val}): Rank ordering violation: Rank {r_num} after Rank {prev_rank}"
                )
            prev_rank = r_num

            data_rows.append({
                "file": file_val,
                "id": str(id_val),
                "correct": c_num,
                "marks": float(m_num),
                "wrong": w_num,
                "unattempted": u_num,
                "rank": r_num
            })

        wb.close()

        # Check total rows against expected count
        if expected_student_count is not None and len(data_rows) != expected_student_count:
            errors.append(
                f"Row count mismatch: Workbook contains {len(data_rows)} students, expected {expected_student_count}."
            )

        summary = {
            "total_students": len(data_rows),
            "top_student": data_rows[0] if data_rows else None,
            "max_score": max((r["marks"] for r in data_rows), default=0.0),
            "min_score": min((r["marks"] for r in data_rows), default=0.0),
            "file_path": str(file_path)
        }

        return len(errors) == 0, errors, summary

