"""Unit tests for dynamic.identity_crops (review crops for the
identity-extract script).

The crops dict must have the same keys the fixed reader's crops dict
has, so extract_identities_to_excel.py can save and display them the
same way. No OCR is needed here: crops are pure image slicing.
"""

import numpy as np

from app.omr.dynamic import (
    BoxRow,
    DynamicIdentity,
    identity_crops,
)


def _identity():
    return DynamicIdentity(
        hall_ticket="AP05CJ1799",
        name="RAMARAO",
        hall_ticket_row=BoxRow(y=70, y1=50, y2=90, x1=100, x2=600,
                               box_w=50.0, box_h=40.0, num_boxes=10),
        name_row=BoxRow(y=130, y1=110, y2=150, x1=100, x2=600,
                        box_w=50.0, box_h=40.0, num_boxes=10),
        confidence=0.9,
    )


def test_identity_crops_has_all_keys():
    img = np.full((400, 800, 3), 255, dtype=np.uint8)
    crops = identity_crops(img, _identity())
    assert set(crops) >= {
        "ht_raw", "ht_processed", "name_raw", "name_processed",
        "ht_missing_on_sheet",
    }
    assert crops["ht_missing_on_sheet"] is False
    assert crops["ht_raw"].size > 0
    assert crops["ht_processed"].size > 0
    assert crops["name_raw"].size > 0
    assert crops["name_processed"].size > 0
    # Processed strip is the zoomed + padded version of the raw strip.
    assert crops["ht_processed"].shape[0] > crops["ht_raw"].shape[0]
    assert crops["ht_processed"].shape[1] > crops["ht_raw"].shape[1]


def test_identity_crops_missing_row_gives_blank_placeholder():
    ident = DynamicIdentity(
        hall_ticket="", name="RAMARAO",
        hall_ticket_row=None,
        name_row=BoxRow(y=130, y1=110, y2=150, x1=100, x2=600,
                        box_w=50.0, box_h=40.0, num_boxes=10),
        confidence=0.7,
    )
    img = np.full((400, 800, 3), 255, dtype=np.uint8)
    crops = identity_crops(img, ident)
    assert crops["ht_missing_on_sheet"] is True
    assert crops["ht_raw"].size > 0
    assert crops["ht_processed"].size > 0
    # Blank white placeholder, not an empty array (cv2.imwrite needs pixels).
    assert crops["ht_raw"].shape == (50, 200, 3)
