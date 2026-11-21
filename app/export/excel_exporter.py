"""Microsoft Excel (.xlsx) result workbook generator strictly conforming to reference format."""
from pathlib import Path
from typing import List, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from app.models.entities import ProcessedSheet, Examination
from app.config.constants import EXPORTS_DIR


class ExcelExporter:
    """Exports certified examination results matching the exact reference column schema."""

    COLUMNS = [
        "File",
        "Hall Ticket Number/Name",
        "Correct",
        "Correct Marks",
        "Wrong",
        "Unattempted",
        "Student Rank"
    ]

    @classmethod
    def export_results(
        cls,
        exam: Examination,
        sheets: List[ProcessedSheet],
        output_path: Optional[Path] = None,
        include_audit: bool = True
    ) -> Path:
        """
        Generates a professionally styled Microsoft Excel (.xlsx) workbook.
        Sorts rows by student rank ascending, then deterministic tie-break.
        """
        if output_path is None:
            filename = f"Results_{exam.code}_{len(sheets)}_Students.xlsx"
            output_path = EXPORTS_DIR / filename
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Examination Results"

        # Styling definitions
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        data_font = Font(name="Calibri", size=11)
        align_left = Alignment(horizontal="left", vertical="center")
        align_center = Alignment(horizontal="center", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")

        thin_border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9")
        )

        # Write Header Row
        ws.row_dimensions[1].height = 28
        for col_idx, col_name in enumerate(cls.COLUMNS, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border

        # Sort sheets by rank ascending
        sorted_sheets = sorted(
            [s for s in sheets if s.status != "REJECTED"],
            key=lambda s: (s.student_rank, -s.total_marks, s.display_identifier)
        )

        # Write Data Rows
        for row_idx, sheet in enumerate(sorted_sheets, start=2):
            ws.row_dimensions[row_idx].height = 20

            # 1. File
            c1 = ws.cell(row=row_idx, column=1, value=sheet.file_name or sheet.file_path)
            c1.font = data_font
            c1.alignment = align_left
            c1.border = thin_border

            # 2. Hall Ticket Number/Name (Explicitly formatted as Text)
            c2 = ws.cell(row=row_idx, column=2, value=sheet.display_identifier)
            c2.font = data_font
            c2.number_format = "@"
            c2.alignment = align_left
            c2.border = thin_border

            # 3. Correct
            c3 = ws.cell(row=row_idx, column=3, value=sheet.correct_count)
            c3.font = data_font
            c3.number_format = "0"
            c3.alignment = align_right
            c3.border = thin_border

            # 4. Correct Marks (Two decimal places)
            c4 = ws.cell(row=row_idx, column=4, value=sheet.total_marks)
            c4.font = data_font
            c4.number_format = "0.00"
            c4.alignment = align_right
            c4.border = thin_border

            # 5. Wrong
            c5 = ws.cell(row=row_idx, column=5, value=sheet.wrong_count)
            c5.font = data_font
            c5.number_format = "0"
            c5.alignment = align_right
            c5.border = thin_border

            # 6. Unattempted
            c6 = ws.cell(row=row_idx, column=6, value=sheet.unattempted_count)
            c6.font = data_font
            c6.number_format = "0"
            c6.alignment = align_right
            c6.border = thin_border

            # 7. Student Rank
            c7 = ws.cell(row=row_idx, column=7, value=sheet.student_rank)
            c7.font = data_font
            c7.number_format = "0"
            c7.alignment = align_right
            c7.border = thin_border

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        # Optional Audit Worksheet
        if include_audit:
            ws_meta = wb.create_sheet(title="Audit Metadata")
            ws_meta.append(["Property", "Value"])
            ws_meta.append(["Examination Code", exam.code])
            ws_meta.append(["Examination Name", exam.name])
            ws_meta.append(["Total Evaluated Students", len(sorted_sheets)])
            ws_meta.append(["Mark per Correct", f"{exam.correct_mark:.2f}"])
            ws_meta.append(["Mark per Wrong", f"{exam.wrong_mark:.2f}"])
            ws_meta.append(["Mark per Unattempted", f"{exam.unattempted_mark:.2f}"])
            ws_meta.append(["Total Form Questions", exam.total_questions])
            ws_meta.column_dimensions["A"].width = 25
            ws_meta.column_dimensions["B"].width = 35

        wb.save(str(output_path))
        wb.close()
        return output_path

