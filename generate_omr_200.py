"""
OMR 200-Question Answer Sheet Generator (Client Redesign)
=========================================================
Generates a print-ready vector PDF and high-resolution master PNGs for the 200-Question
OMR Answer Sheet, featuring the exact Syam Institute header branding, candidate details layout,
shaded question columns with optical calibration bars, ballpoint pen illustration, and
calibrated 5-column x 40-row bubble grid template.
"""

import sys
from pathlib import Path
import cv2
import numpy as np
import pymupdf
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from app.config.constants import (
    TOTAL_QUESTIONS_200, QUESTIONS_PER_COLUMN_200, NUM_COLUMNS_200,
    COLUMN_BASE_X_200, OPTION_PITCH_X_200, ROW_BASE_Y_200, ROW_PITCH_Y_200,
    TIMING_MARK_EXPECTED_COUNT_200
)


def create_omr_200_sheet(pdf_path: str, png_200_path: str = None, png_300_path: str = None):
    # Standard A4 page (595.27559 x 841.88976 points)
    # Coordinate system scaled to 200 DPI frame: 1653.54 x 2338.58 pixels
    canvas_w, canvas_h = 1653.54, 2338.58

    c = canvas.Canvas(pdf_path, pagesize=A4)
    c.scale(72.0 / 200.0, 72.0 / 200.0)

    # Color palette matching official OMR sheet
    OMR_RED = colors.HexColor("#C8102E")      # Standard OMR Dropout Red (Pantone 185C)
    OMR_DARK_RED = colors.HexColor("#9E0B21") # Dark accent red for titles & field labels
    OMR_PINK_BG = colors.HexColor("#FDEEF2")  # Light pink column background tint
    BLACK = colors.HexColor("#000000")        # Solid black for timing marks & fiducials

    def to_rl_y(y_top):
        """Converts top-down Y coordinate to ReportLab bottom-up Y coordinate."""
        return canvas_h - y_top

    # =========================================================================
    # 1. TOP HEADER BANNER: SYAM INSTITUTE
    # =========================================================================
    banner_w = 1300.0
    banner_h = 110.0
    banner_x = (canvas_w - banner_w) / 2.0
    banner_y = 14.0

    if Path("syam_banner_hq.png").exists():
        c.drawImage("syam_banner_hq.png", banner_x, to_rl_y(banner_y + banner_h), width=banner_w, height=banner_h)
    else:
        # Fallback vector banner block if image not present
        c.setFillColor(BLACK)
        c.roundRect(banner_x, to_rl_y(banner_y + banner_h), banner_w, banner_h, 8, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 26)
        c.drawCentredString(canvas_w / 2.0, to_rl_y(banner_y + 60.0), "SYAM INSTITUTE - SINCE 2001")

    # =========================================================================
    # 2. PERIMETER FIDUCIALS, TIMING TRACKS & MARGINS
    # =========================================================================
    # Corner registration blocks (solid black squares) at inner margin
    sq_size = 28.0
    c.setFillColor(BLACK)
    for sy in (140.0, 435.0, 725.0, 1025.0, 2245.0):
        c.rect(158.0, to_rl_y(sy + sq_size), sq_size, sq_size, fill=1, stroke=0)
        c.rect(1468.0, to_rl_y(sy + sq_size), sq_size, sq_size, fill=1, stroke=0)

    # Black fiducial circles (dots) at inner margins matching physical sheet
    for dy in (190.0, 440.0, 780.0, 1050.0, 1260.0, 1710.0, 2100.0, 2210.0):
        c.circle(172.0, to_rl_y(dy), 9.0, fill=1, stroke=0)
        c.circle(1482.0, to_rl_y(dy), 9.0, fill=1, stroke=0)

    # Exactly 56 Timing Marks on Left and Right Margins
    # Mark dimensions: width=42px, height=14px
    tm_w = 42.0
    tm_h = 14.0
    tm_left_x = 97.0
    tm_right_x = 1517.0

    timing_y_list = []
    # Upper section (Marks 0 to 13)
    for i in range(14):
        timing_y_list.append(410.0 + i * 27.0)
    # Section divider marks (Marks 14 and 15)
    timing_y_list.append(1033.0)
    timing_y_list.append(1062.0)
    # Answer grid question rows (Marks 16 to 55)
    for i in range(40):
        timing_y_list.append(ROW_BASE_Y_200 + i * ROW_PITCH_Y_200)

    for ty in timing_y_list:
        c.rect(tm_left_x, to_rl_y(ty + tm_h / 2.0), tm_w, tm_h, fill=1, stroke=0)
        c.rect(tm_right_x, to_rl_y(ty + tm_h / 2.0), tm_w, tm_h, fill=1, stroke=0)

    # Dotted perforation margin guides
    c.setStrokeColor(OMR_RED)
    c.setLineWidth(1.0)
    c.setDash([3, 4])
    c.line(55.0, 50.0, 55.0, canvas_h - 50.0)
    c.line(canvas_w - 55.0, 50.0, canvas_w - 55.0, canvas_h - 50.0)
    c.setDash([])

    # Vertical instructions text along left margin
    c.saveState()
    c.translate(40.0, to_rl_y(1250.0))
    c.rotate(90)
    c.setFont("Helvetica-Bold", 9.5)
    c.setFillColor(OMR_DARK_RED)
    c.drawCentredString(0, 0, "✂  INSTRUCTIONS TO INVIGILATOR : PLEASE FOLD AT PERFORATION AND THEN TEAR EXAMINATION IS OVER  ✂")
    c.restoreState()

    # Scissor symbols along right perforation line
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(OMR_RED)
    for sy in (180.0, 500.0, 850.0, 1300.0, 1800.0):
        c.drawString(canvas_w - 65.0, to_rl_y(sy), "✂")

    # =========================================================================
    # 3. HEADER: STUDENT DETAILS (Exact Placement Preserved)
    # =========================================================================
    # Form Title
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(OMR_DARK_RED)
    c.drawCentredString(canvas_w / 2.0, to_rl_y(144.0), "OMR ANSWER SHEET OF WRITTEN TEST")

    # Helper to draw character boxes
    def draw_char_boxes(start_x, start_y, box_count, box_w=28.0, box_h=28.0):
        c.setStrokeColor(OMR_RED)
        c.setLineWidth(1.2)
        c.setFillColor(colors.white)
        for b_idx in range(box_count):
            bx = start_x + b_idx * box_w
            c.rect(bx, to_rl_y(start_y + box_h), box_w, box_h, fill=1, stroke=1)

    labels_info = [
        ("Hall Ticket Number", "(capital Letter's Only)", 16, 168.0),
        ("Name of the Candidate", "(capital Letter's Only)", 24, 210.0),
        ("Gender", "", 8, 252.0),
        ("Community", "", 14, 294.0),
        ("District", "", 21, 336.0),
    ]

    label_x = 180.0
    colon_x = 425.0
    boxes_start_x = 445.0

    for main_lbl, sub_lbl, num_boxes, y_pos in labels_info:
        c.setFillColor(OMR_DARK_RED)
        c.setFont("Helvetica-Bold", 12.5)
        c.drawString(label_x, to_rl_y(y_pos + 14), main_lbl)
        if sub_lbl:
            c.setFont("Helvetica", 8.5)
            c.drawString(label_x, to_rl_y(y_pos + 25), sub_lbl)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(colon_x, to_rl_y(y_pos + 17), ":")
        draw_char_boxes(boxes_start_x, y_pos, num_boxes, box_w=28.0, box_h=28.0)

    # Test Centre and Date & Time underline fields
    c.setFont("Helvetica-Bold", 12.5)
    c.setFillColor(OMR_DARK_RED)
    c.drawString(label_x, to_rl_y(380.0), "Test centre code &Name")
    c.drawString(colon_x, to_rl_y(380.0), ":")
    c.setStrokeColor(OMR_RED)
    c.setLineWidth(1.0)
    c.line(boxes_start_x, to_rl_y(383.0), 1033.0, to_rl_y(383.0))

    c.drawString(label_x, to_rl_y(414.0), "Date & Time of Exam")
    c.drawString(colon_x, to_rl_y(414.0), ":")
    c.line(boxes_start_x, to_rl_y(417.0), 1033.0, to_rl_y(417.0))

    # Photograph Box (Right side of header)
    photo_x = 1250.0
    photo_y = 168.0
    photo_w = 190.0
    photo_h = 230.0
    c.setStrokeColor(OMR_RED)
    c.setLineWidth(1.5)
    c.rect(photo_x, to_rl_y(photo_y + photo_h), photo_w, photo_h, fill=0, stroke=1)
    c.setFont("Helvetica", 9)
    c.setFillColor(OMR_RED)
    c.drawCentredString(photo_x + photo_w / 2.0, to_rl_y(photo_y + photo_h / 2.0 + 8), "AFFIX LATEST")
    c.drawCentredString(photo_x + photo_w / 2.0, to_rl_y(photo_y + photo_h / 2.0 - 6), "PASSPORT SIZE")
    c.drawCentredString(photo_x + photo_w / 2.0, to_rl_y(photo_y + photo_h / 2.0 - 20), "PHOTOGRAPH HERE")

    # =========================================================================
    # 4. MIDDLE SECTION: BOOKLET INFO & INSTRUCTIONS & SIGNATURES
    # =========================================================================
    # 1. Q.P. Booklet Number (Left column)
    bk_x = 165.0
    bk_y = 455.0
    bk_w = 175.0
    bk_h = 245.0
    c.setStrokeColor(OMR_RED)
    c.setLineWidth(1.2)
    c.roundRect(bk_x, to_rl_y(bk_y + bk_h), bk_w, bk_h, 6, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(OMR_DARK_RED)
    c.drawString(bk_x + 8, to_rl_y(bk_y + 16), "1. Q.P. Booklet Number")

    num_digits = 6
    d_box_w = 26.0
    d_box_h = 24.0
    start_d_x = bk_x + (bk_w - num_digits * d_box_w) / 2.0
    d_box_y = bk_y + 24.0
    for d in range(num_digits):
        c.rect(start_d_x + d * d_box_w, to_rl_y(d_box_y + d_box_h), d_box_w, d_box_h, fill=0, stroke=1)

    digit_bubble_r = 7.5
    for col in range(num_digits):
        cx = start_d_x + col * d_box_w + d_box_w / 2.0
        for row in range(10):
            cy = d_box_y + d_box_h + 12.0 + row * 18.0
            c.circle(cx, to_rl_y(cy), digit_bubble_r, fill=0, stroke=1)
            c.setFont("Helvetica", 7.5)
            c.drawCentredString(cx, to_rl_y(cy) - 2.5, str(row))

    # 2. Q.P. Booklet Code & 3. Shade Booklet Code
    bc_x = bk_x + bk_w + 12.0
    bc_y = 455.0
    bc_w = 155.0
    bc_h = 245.0
    c.roundRect(bc_x, to_rl_y(bc_y + bc_h), bc_w, bc_h, 6, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(bc_x + 10, to_rl_y(bc_y + 16), "2. Q.P. Booklet Code")
    c.rect(bc_x + 60.0, to_rl_y(bc_y + 24.0 + 36.0), 36.0, 36.0, fill=0, stroke=1)

    c.line(bc_x, to_rl_y(bc_y + 70.0), bc_x + bc_w, to_rl_y(bc_y + 70.0))
    c.drawString(bc_x + 6, to_rl_y(bc_y + 86.0), "3. Shade the Booklet Code")
    c.setFont("Helvetica", 8)
    c.drawString(bc_x + 18, to_rl_y(bc_y + 100.0), "(Refer code Printed")
    c.drawString(bc_x + 28, to_rl_y(bc_y + 112.0), "on Q.P. Booklet)")

    b_opts = ("A", "B", "C", "D")
    b_opt_y = bc_y + 150.0
    for idx, opt in enumerate(b_opts):
        bx = bc_x + 18.0 + idx * 34.0
        c.circle(bx, to_rl_y(b_opt_y), 11.0, fill=0, stroke=1)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(bx, to_rl_y(b_opt_y) - 3.0, opt)

    # Instructions to Invigilator Box
    inst_x = 790.0
    inst_y = 430.0
    inst_w = 670.0
    inst_h = 105.0
    c.setStrokeColor(OMR_RED)
    c.setLineWidth(1.2)
    c.rect(inst_x, to_rl_y(inst_y + inst_h), inst_w, inst_h, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 9.5)
    c.setFillColor(OMR_DARK_RED)
    c.drawString(inst_x + 8, to_rl_y(inst_y + 14), "Instructions to the invigilator :")

    inst_texts = [
        "1. The name, photo and H.T. number of this candidate are tallied with that of Hall Ticket details.",
        "2. I have provided the same question booklet code as printed on the OMR sheet at S.No.2.",
        "3. Q.P Booklet Number and Booklet Code have been entered / bubbled by the candidate at S.No.",
        "    1 and 3 and the same is compared with the Question paper booklet supplied to the Candidate and is tallying."
    ]
    c.setFont("Helvetica", 8)
    c.setFillColor(OMR_RED)
    for l_idx, line_t in enumerate(inst_texts):
        c.drawString(inst_x + 8, to_rl_y(inst_y + 30 + l_idx * 16.0), line_t)

    # Barcode & Candidate Signature & Invigilator Signature
    sig_area_y = 545.0
    barcode_x = 790.0
    barcode_w = 95.0
    barcode_h = 155.0
    c.rect(barcode_x, to_rl_y(sig_area_y + barcode_h), barcode_w, barcode_h, fill=0, stroke=1)
    c.setFillColor(BLACK)
    for bx_idx in range(int(barcode_x + 6), int(barcode_x + barcode_w - 6), 4):
        bar_thickness = 1.5 if (bx_idx % 3 != 0) else 3.0
        c.rect(bx_idx, to_rl_y(sig_area_y + barcode_h - 8), bar_thickness, barcode_h - 16, fill=1, stroke=0)

    # Candidate Signature Box
    cand_sig_x = barcode_x + barcode_w + 10.0
    cand_sig_w = 425.0
    cand_sig_h = 155.0
    c.setStrokeColor(OMR_RED)
    c.rect(cand_sig_x, to_rl_y(sig_area_y + cand_sig_h), cand_sig_w, cand_sig_h, fill=0, stroke=1)
    c.line(cand_sig_x, to_rl_y(sig_area_y + 70.0), cand_sig_x + cand_sig_w, to_rl_y(sig_area_y + 70.0))
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(OMR_DARK_RED)
    c.drawCentredString(cand_sig_x + cand_sig_w / 2.0, to_rl_y(sig_area_y + 84.0), "Signature of the Candidate")

    # Binary check pattern below signature
    c.setStrokeColor(OMR_RED)
    pat_y = sig_area_y + 115.0
    for p_col in range(6):
        px = cand_sig_x + 35.0 + p_col * 60.0
        c.circle(px, to_rl_y(pat_y), 10.0, fill=0, stroke=1)
        c.setFillColor(BLACK if p_col % 2 == 0 else colors.white)
        c.rect(px - 9.0, to_rl_y(pat_y + 30.0), 18.0, 18.0, fill=(1 if p_col % 2 == 0 else 0), stroke=1)

    # Invigilator Signature Vertical Box
    inv_sig_x = cand_sig_x + cand_sig_w + 10.0
    inv_sig_w = 130.0
    inv_sig_h = 155.0
    c.setStrokeColor(OMR_RED)
    c.rect(inv_sig_x, to_rl_y(sig_area_y + inv_sig_h), inv_sig_w, inv_sig_h, fill=0, stroke=1)

    c.saveState()
    c.translate(inv_sig_x + inv_sig_w / 2.0 + 4, to_rl_y(sig_area_y + inv_sig_h / 2.0))
    c.rotate(90)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(OMR_DARK_RED)
    c.drawCentredString(0, 0, "Signature of the Invigilator")
    c.restoreState()

    # Section 4: Handwritten Undertaking
    und_y = 718.0
    c.setFont("Helvetica-Bold", 9.5)
    c.setFillColor(OMR_DARK_RED)
    und_text = (
        "4. I hereby give an undertaking that I will return the OMR answer sheet to the invigilator and "
        "agree that I have not indulged in any malpractice"
    )
    und_text_2 = (
        "/ unlawful / illegal activity in connection with this examination. "
        "(In your own running handwriting reproduce this paragraph below)."
    )
    c.drawString(165.0, to_rl_y(und_y + 12.0), und_text)
    c.drawString(180.0, to_rl_y(und_y + 26.0), und_text_2)

    c.setStrokeColor(OMR_RED)
    c.setLineWidth(0.8)
    c.setDash([2, 4])
    for line_idx in range(3):
        ly = und_y + 55.0 + line_idx * 30.0
        c.line(165.0, to_rl_y(ly), 1460.0, to_rl_y(ly))
    c.setDash([])

    # Divider line with "ANSWERS"
    div_y = 1030.0
    c.setStrokeColor(OMR_RED)
    c.setLineWidth(1.5)
    c.line(165.0, to_rl_y(div_y), 690.0, to_rl_y(div_y))
    c.line(950.0, to_rl_y(div_y), 1460.0, to_rl_y(div_y))
    # Arrow heads
    c.line(165.0, to_rl_y(div_y), 175.0, to_rl_y(div_y - 4))
    c.line(165.0, to_rl_y(div_y), 175.0, to_rl_y(div_y + 4))
    c.line(1460.0, to_rl_y(div_y), 1450.0, to_rl_y(div_y - 4))
    c.line(1460.0, to_rl_y(div_y), 1450.0, to_rl_y(div_y + 4))

    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(OMR_DARK_RED)
    c.drawCentredString(canvas_w / 2.0, to_rl_y(div_y - 5.0), "ANSWERS")

    # =========================================================================
    # 5. 200-QUESTION BUBBLE GRID WITH SHADED COLUMNS & CALIBRATION BARS
    # (Exact bubble centers COLUMN_BASE_X_200, ROW_BASE_Y_200, ROW_PITCH_Y_200 preserved)
    # =========================================================================
    col_bases_x = list(COLUMN_BASE_X_200)
    opt_pitch_x = OPTION_PITCH_X_200
    bubble_radius = 8.5
    options = ("1", "2", "3", "4")  # Numeric options matching official Syam Institute OMR sheet

    # Draw shaded background rounded boxes and optical calibration bars for all 5 columns
    for col_idx, base_x in enumerate(col_bases_x):
        box_x = base_x - 48.0
        box_w = 3 * opt_pitch_x + 76.0  # Spans from question number to beyond option 4

        # Shaded rounded background box
        c.setFillColor(OMR_PINK_BG)
        c.setStrokeColor(OMR_RED)
        c.setLineWidth(1.2)
        c.roundRect(box_x, to_rl_y(2175.0), box_w, 2175.0 - 1080.0, 6, fill=1, stroke=1)

        # 4 Black calibration bars at top (above options 1, 2, 3, 4)
        c.setFillColor(BLACK)
        for opt_idx in range(4):
            bx = base_x + opt_idx * opt_pitch_x
            c.rect(bx - 7.0, to_rl_y(1062.0), 14.0, 20.0, fill=1, stroke=0)
            c.rect(bx - 7.0, to_rl_y(2206.0), 14.0, 20.0, fill=1, stroke=0)

    # 40 Question Rows in each column
    c.setLineWidth(1.0)
    for row_idx in range(40):
        cy = ROW_BASE_Y_200 + row_idx * ROW_PITCH_Y_200
        rl_y = to_rl_y(cy)

        for col_idx in range(5):
            q_num = col_idx * 40 + row_idx + 1
            base_x = col_bases_x[col_idx]

            # Question number in bold dark red
            c.setFont("Helvetica-Bold", 9.5)
            c.setFillColor(OMR_DARK_RED)
            c.drawRightString(base_x - 14.0, rl_y - 3.2, f"{q_num:3d}")

            # 4 Bubbles (1, 2, 3, 4)
            c.setStrokeColor(OMR_RED)
            for opt_idx, opt in enumerate(options):
                bx = base_x + opt_idx * opt_pitch_x
                c.circle(bx, rl_y, bubble_radius, fill=0, stroke=1)
                c.setFont("Helvetica-Bold", 7.5)
                c.setFillColor(OMR_RED)
                c.drawCentredString(bx, rl_y - 2.8, opt)

    # Ballpoint Pen Illustration on right of Column 5
    if Path("pen_graphic.png").exists():
        c.drawImage("pen_graphic.png", 1395.0, to_rl_y(2050.0), width=48.0, height=800.0, mask="auto")

    c.save()
    print(f"Generated Vector PDF: {pdf_path}")

    # Render high-resolution master PNG images
    doc = pymupdf.open(pdf_path)
    page = doc[0]

    if png_200_path:
        pix200 = page.get_pixmap(dpi=200)
        pix200.save(png_200_path)
        print(f"Rendered 200 DPI PNG: {png_200_path} ({pix200.width}x{pix200.height})")

    if png_300_path:
        pix300 = page.get_pixmap(dpi=300)
        pix300.save(png_300_path)
        print(f"Rendered 300 DPI PNG: {png_300_path} ({pix300.width}x{pix300.height})")

    doc.close()


if __name__ == "__main__":
    out_pdf = "OMR_200_Sheet_Template.pdf"
    out_png_200 = "OMR_200_Sheet_Template.png"
    out_png_300 = "OMR_200_Sheet_Template_300DPI.png"
    create_omr_200_sheet(out_pdf, out_png_200, out_png_300)
