"""Character Box Segmentation and Morphological Grid Line Removal for Student Identification."""
import cv2
import numpy as np
from typing import List, Tuple, Optional
from app.config.constants import (
    HT_FIELD_X_START, HT_FIELD_Y_START, HT_BOX_PITCH,
    HT_BOX_INNER_W, HT_BOX_INNER_H, HT_NUM_BOXES,
    NAME_FIELD_X_START, NAME_FIELD_X_END, NAME_FIELD_Y_START, NAME_FIELD_Y_END
)


class CharacterBoxSegmenter:
    """Extracts isolated character patches from printed OMR character boxes."""

    @classmethod
    def extract_hall_ticket_boxes(cls, image_bgr: np.ndarray) -> List[np.ndarray]:
        """
        Segments the 16 character boxes from the Hall Ticket field.
        Applies red channel dropout to remove red grid lines.
        Returns list of 16 binarized character crops.
        """
        _, _, r = cv2.split(image_bgr)
        boxes = []

        for i in range(HT_NUM_BOXES):
            bx = int(HT_FIELD_X_START + i * HT_BOX_PITCH)
            by = int(HT_FIELD_Y_START)

            # Inner crop away from right and bottom borders
            patch_r = r[by + 2 : by + 2 + HT_BOX_INNER_H, bx + 2 : bx + 2 + HT_BOX_INNER_W]

            # Binarize: dark pen/pencil has low red value (<150)
            char_bin = np.where(patch_r < 150, 0, 255).astype(np.uint8)

            # Clean isolated noise pixels
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            cleaned = cv2.morphologyEx(255 - char_bin, cv2.MORPH_OPEN, kernel)
            char_bin = 255 - cleaned

            boxes.append(char_bin)

        return boxes

    @classmethod
    def extract_candidate_name_strip(cls, image_bgr: np.ndarray) -> np.ndarray:
        """
        Extracts the candidate name field strip with color dropout applied.
        """
        _, _, r = cv2.split(image_bgr)
        name_strip_r = r[NAME_FIELD_Y_START:NAME_FIELD_Y_END, NAME_FIELD_X_START:NAME_FIELD_X_END]
        # Binarize with dropout
        name_bin = np.where(name_strip_r < 150, 0, 255).astype(np.uint8)
        return name_bin

