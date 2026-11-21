"""OMR Image Preprocessing, Registration Mark Alignment, and Color Dropout."""
import cv2
import numpy as np
import pymupdf
from pathlib import Path
from typing import Tuple, Optional, List, Dict
from app.config.constants import (
    REF_CANVAS_WIDTH, REF_CANVAS_HEIGHT,
    LEFT_TRACK_X_MIN, LEFT_TRACK_X_MAX,
    RIGHT_TRACK_X_MIN, RIGHT_TRACK_X_MAX
)

# Calibrated Master Fiducial Points across all 49 timing marks on both margins (98 points total)
REF_TIMING_POINTS = np.float32([
    [130.0, 199.0], [129.5, 240.5], [129.0, 282.5], [128.5, 323.5], [128.0, 365.5],
    [128.0, 407.0], [127.5, 448.0], [127.5, 491.0], [127.0, 534.0], [127.0, 577.5],
    [127.0, 619.5], [127.0, 661.0], [126.5, 703.0], [127.0, 744.0], [126.5, 785.0],
    [127.0, 826.0], [127.0, 867.0], [127.0, 908.0], [127.0, 950.5], [126.5, 992.0],
    [126.5, 1034.0], [126.5, 1076.0], [126.5, 1118.0], [126.5, 1159.5], [126.5, 1201.0],
    [126.5, 1242.0], [126.5, 1284.0], [126.5, 1325.5], [126.0, 1367.0], [126.0, 1408.0],
    [126.0, 1449.0], [126.0, 1490.0], [126.0, 1530.5], [126.0, 1571.5], [126.0, 1612.0],
    [125.5, 1652.5], [125.5, 1694.0], [125.5, 1735.5], [125.5, 1777.0], [125.0, 1818.5],
    [125.0, 1860.0], [125.0, 1902.0], [125.0, 1943.0], [125.0, 1984.5], [125.0, 2026.0],
    [124.5, 2067.0], [124.5, 2109.0], [124.5, 2150.0], [124.5, 2188.0],
    [1525.0, 221.0], [1524.5, 261.0], [1524.0, 301.0], [1523.5, 341.0], [1523.5, 381.5],
    [1523.0, 421.5], [1522.5, 461.5], [1522.5, 503.0], [1522.5, 545.0], [1522.5, 587.0],
    [1521.5, 627.0], [1521.5, 667.0], [1521.5, 708.0], [1521.5, 748.0], [1521.5, 789.0],
    [1521.5, 830.0], [1521.5, 870.5], [1521.5, 913.0], [1521.5, 954.5], [1521.5, 996.0],
    [1521.5, 1038.0], [1521.5, 1080.0], [1521.5, 1122.0], [1521.0, 1163.0], [1521.5, 1204.5],
    [1521.5, 1246.5], [1521.0, 1288.5], [1521.0, 1330.0], [1521.0, 1371.5], [1521.0, 1412.0],
    [1521.0, 1453.0], [1520.5, 1494.5], [1520.5, 1535.0], [1520.5, 1576.0], [1520.5, 1616.5],
    [1520.5, 1658.0], [1520.5, 1699.5], [1520.5, 1740.5], [1520.5, 1782.0], [1520.5, 1823.5],
    [1520.5, 1865.0], [1520.5, 1906.5], [1519.5, 1947.5], [1519.5, 1989.5], [1519.5, 2030.5],
    [1519.5, 2072.0], [1519.5, 2114.0], [1519.5, 2155.0], [1519.5, 2194.0]
])

REF_CORNER_POINTS = np.float32([
    [130.0, 199.0], [124.5, 2188.0], [1525.0, 221.0], [1519.5, 2194.0]
])

REF_CORNER_POINTS_200 = np.float32([
    [110.0, 410.0], [112.0, 2271.0], [1578.0, 410.0], [1562.0, 2279.0]
])



class Preprocessor:
    """Preprocesses raw scans, detects timing tracks, corrects skew, and extracts dropout ink."""

    @staticmethod
    def load_image(file_path: Path) -> np.ndarray:
        """Loads an image from disk supporting JPG, PNG, TIFF, or PDF."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")

        ext = file_path.suffix.lower()
        if ext == ".pdf":
            doc = pymupdf.open(str(file_path))
            if len(doc) == 0:
                raise ValueError(f"Empty PDF document: {file_path}")
            page = doc[0]
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            doc.close()
            return img
        else:
            img = cv2.imread(str(file_path), cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError(f"Failed to decode image file: {file_path}")
            return img

    @staticmethod
    def extract_ink_channel(image_bgr: np.ndarray) -> np.ndarray:
        """
        Isolates black/blue ballpoint pen and graphite markings using Red Dropout separation.
        Formula: I_ink = 255 - R
        This drops out printed red/orange guidelines and highlights student marks.
        """
        _, _, r = cv2.split(image_bgr)
        ink_map = (255 - r).astype(np.float32)
        return ink_map

    @classmethod
    def detect_timing_tracks(
        cls, image_bgr: np.ndarray
    ) -> Tuple[List[Tuple[int, int, int, int]], List[Tuple[int, int, int, int]], float]:
        """
        Detects left and right timing marks along the margins.
        Returns: (left_marks, right_marks, skew_angle_deg)
        """
        h, w = image_bgr.shape[:2]
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 110, 255, cv2.THRESH_BINARY_INV)

        left_band_xmax = int(w * 0.15)
        right_band_xmin = int(w * 0.85)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        left_marks = []
        right_marks = []

        scale_x = w / float(REF_CANVAS_WIDTH)
        scale_y = h / float(REF_CANVAS_HEIGHT)

        min_w = int(35 * scale_x)
        max_w = int(60 * scale_x)
        min_h = int(12 * scale_y)
        max_h = int(30 * scale_y)

        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            area = cv2.contourArea(c)
            if min_w <= bw <= max_w and min_h <= bh <= max_h and area > (400 * scale_x * scale_y):
                aspect = float(bw) / float(bh)
                if 1.8 <= aspect <= 3.5:
                    if x < left_band_xmax:
                        left_marks.append((x, y, bw, bh))
                    elif x > right_band_xmin:
                        right_marks.append((x, y, bw, bh))

        left_marks.sort(key=lambda m: m[1])
        right_marks.sort(key=lambda m: m[1])

        # Compute skew angle
        skew_angle = 0.0
        if len(left_marks) >= 5 and len(right_marks) >= 5:
            top_left = left_marks[0]
            top_right = right_marks[0]
            dx = top_right[0] - top_left[0]
            dy = top_right[1] - top_left[1]
            if dx > 0:
                skew_angle = float(np.degrees(np.arctan2(dy, dx)))

        return left_marks, right_marks, skew_angle

    @classmethod
    def align_and_deskew(
        cls, image_bgr: np.ndarray, target_w: int = REF_CANVAS_WIDTH, target_h: int = REF_CANVAS_HEIGHT
    ) -> Tuple[np.ndarray, float]:
        """
        Normalizes canvas dimensions and aligns image using dual 49-timing tracks.
        Uses full RANSAC affine transform across 98 timing marks when both tracks are complete,
        or 4-corner homography when partial tracks are found.
        Returns: (aligned_image_bgr, detected_skew_angle)
        """
        h, w = image_bgr.shape[:2]

        # 1. Scale normalization if scan resolution differs substantially
        if abs(w - target_w) > 30 or abs(h - target_h) > 60:
            image_bgr = cv2.resize(image_bgr, (target_w, target_h), interpolation=cv2.INTER_AREA)

        # 2. Timing mark detection
        left_marks, right_marks, skew_angle = cls.detect_timing_tracks(image_bgr)

        # Check if sheet is 200Q (timing mark count >= 53)
        is_200q = (len(left_marks) >= 53 or len(right_marks) >= 53)

        # 3. Dual-track full affine mapping (98 fiducial points for standard 160Q)
        if not is_200q and len(left_marks) == 49 and len(right_marks) == 49:
            src_pts = []
            for m in left_marks:
                src_pts.append([m[0] + m[2] / 2.0, m[1] + m[3] / 2.0])
            for m in right_marks:
                src_pts.append([m[0] + m[2] / 2.0, m[1] + m[3] / 2.0])
            src_pts = np.float32(src_pts)
            M, _ = cv2.estimateAffine2D(src_pts, REF_TIMING_POINTS, method=cv2.RANSAC)
            if M is not None:
                aligned_img = cv2.warpAffine(
                    image_bgr, M, (target_w, target_h),
                    flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
                )
                return aligned_img, skew_angle

        # 4. Fallback 1: 4-Corner Homography if tracks have endpoints
        if len(left_marks) >= 2 and len(right_marks) >= 2:
            tl = [left_marks[0][0] + left_marks[0][2] / 2.0, left_marks[0][1] + left_marks[0][3] / 2.0]
            bl = [left_marks[-1][0] + left_marks[-1][2] / 2.0, left_marks[-1][1] + left_marks[-1][3] / 2.0]
            tr = [right_marks[0][0] + right_marks[0][2] / 2.0, right_marks[0][1] + right_marks[0][3] / 2.0]
            br = [right_marks[-1][0] + right_marks[-1][2] / 2.0, right_marks[-1][1] + right_marks[-1][3] / 2.0]
            src_pts = np.float32([tl, bl, tr, br])
            target_corners = REF_CORNER_POINTS_200 if is_200q else REF_CORNER_POINTS
            H, _ = cv2.findHomography(src_pts, target_corners)
            if H is not None:
                aligned_img = cv2.warpPerspective(
                    image_bgr, H, (target_w, target_h),
                    flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
                )
                return aligned_img, skew_angle

        # 5. Fallback 2: Rotation deskew + anchor translation
        aligned_img = image_bgr.copy()
        if abs(skew_angle) >= 0.5 and abs(skew_angle) < 15.0:
            center = (w / 2.0, h / 2.0)
            rot_mat = cv2.getRotationMatrix2D(center, -skew_angle, 1.0)
            aligned_img = cv2.warpAffine(
                aligned_img, rot_mat, (w, h),
                flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
            )
            left_marks, right_marks, _ = cls.detect_timing_tracks(aligned_img)

        # Anchor translation fallback
        if left_marks:
            ref_tl_x = 110.0 if is_200q else 106.0
            ref_tl_y = 410.0 if is_200q else 189.0
            tl_x = left_marks[0][0]
            tl_y = left_marks[0][1]
            dx = int(round(tl_x - ref_tl_x))
            dy = int(round(tl_y - ref_tl_y))
            if abs(dx) > 1 or abs(dy) > 1:
                M = np.float32([[1, 0, -dx], [0, 1, -dy]])
                aligned_img = cv2.warpAffine(
                    aligned_img, M, (target_w, target_h),
                    flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
                )

        return aligned_img, skew_angle
