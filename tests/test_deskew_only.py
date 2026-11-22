"""Regression tests for Preprocessor.deskew_only.

Background: on the 200Q Syam sheet (img0077.jpg) the track-warped
``align_and_deskew`` output cut the top of the page off — the first
detected timing mark sat far below the real top of the track, so the
4-corner homography mapped the hall-ticket row to y < 0 and identity
came back blank (old tool) or garbage (dynamic on the warped image).
Dynamic detection finds everything from the image itself, so it runs
on a deskewed-only copy where the whole page stays in frame.
"""
import cv2
import numpy as np
from pathlib import Path

from app.omr.preprocessor import Preprocessor
from app.omr.dynamic import analyze_sheet_dynamic, top_is_cut_off

REPO = Path(__file__).resolve().parent.parent
SAMPLE_160 = REPO / "OMR_325601.jpg"


def test_deskew_only_keeps_shape_and_top_of_page():
    """Deskewing must not resize, crop, or shift content off-canvas."""
    img = cv2.imread(str(SAMPLE_160))
    assert img is not None
    deskewed, skew = Preprocessor.deskew_only(img)
    assert deskewed.shape == img.shape
    # The header/banner ink in the top strip must survive deskewing.
    gray_raw = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray_des = cv2.cvtColor(deskewed, cv2.COLOR_BGR2GRAY)
    top_raw = int(np.sum(gray_raw[:80, :] < 160))
    top_des = int(np.sum(gray_des[:80, :] < 160))
    assert top_raw > 0
    assert top_des > 0.5 * top_raw


def test_deskew_only_blank_image_is_safe():
    blank = np.full((1000, 800, 3), 255, dtype=np.uint8)
    out, _ = Preprocessor.deskew_only(blank)
    assert out.shape == blank.shape
    assert np.all(out == 255)


def test_top_is_cut_off_spots_a_row_touching_the_top_edge():
    """A red box row starting at y=0 means the page top was cut off;
    a normal row lower down must not trigger it."""
    # Boxes must fit find_box_rows' height band (6..4.5% of image
    # height), so keep them 12px tall in a 400px-tall image.
    cut = np.full((400, 600, 3), 255, dtype=np.uint8)
    # Row of red-outlined boxes touching the top edge (y1 == 0).
    for i in range(10):
        x = 100 + i * 30
        cv2.rectangle(cut, (x, 0), (x + 28, 12), (0, 0, 255), 2)
    assert top_is_cut_off(cut) is True

    ok = np.full((400, 600, 3), 255, dtype=np.uint8)
    for i in range(10):
        x = 100 + i * 30
        cv2.rectangle(ok, (x, 100), (x + 28, 112), (0, 0, 255), 2)
    assert top_is_cut_off(ok) is False


def test_dynamic_on_deskewed_160q_sample_finds_160():
    """Dynamic detection on the deskewed (not warped) 160Q sample
    must still find all 160 questions, as it did on the warped image."""
    img = cv2.imread(str(SAMPLE_160))
    assert img is not None
    deskewed, _ = Preprocessor.deskew_only(img)
    sheet = analyze_sheet_dynamic(deskewed, expected_questions=160,
                                  ocr_engine=None)
    assert sheet.method == "dynamic"
    assert sheet.found_questions == 160
