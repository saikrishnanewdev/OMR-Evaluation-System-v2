"""
Offline OCR Engine for Candidate Identification (Hall Ticket and Name).
Performs purely dynamic, local computer vision and neural text recognition.
Incorporates 2.5x bicubic zooming and optical red-color dropout to remove
all pre-printed red/pink box lines, borders, and labels before text extraction.
Zero cloud dependencies, zero hardcoded student tables.
"""
import os
import cv2
import re
import unicodedata
import numpy as np
from pathlib import Path
from typing import Tuple, List, Optional, Dict
from rapidocr_onnxruntime import RapidOCR
try:
    # Optional: only used to point at a local Tesseract binary if one
    # is installed. All real OCR goes through RapidOCR below, so the
    # app must NOT crash at startup when this package is missing —
    # that is what broke the first built .exe (ModuleNotFoundError).
    import pytesseract
except ImportError:  # pragma: no cover - missing optional dependency
    pytesseract = None



# Configure local offline Tesseract binary path if available
if pytesseract is not None:
    TESSERACT_CANDIDATE_PATHS = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")
    ]
    for p in TESSERACT_CANDIDATE_PATHS:
        if os.path.exists(p):
            pytesseract.pytesseract.tesseract_cmd = p
            break


def _digit_agreement(a: str, b: str) -> float:
    """Position-wise agreement of two digit strings (0.0-1.0).

    Roll numbers are fixed-format IDs: the digits must agree in
    position, not merely appear somewhere in the string. A
    SequenceMatcher ratio is too lenient here — '01624' vs '01562'
    scores 0.8 (the 6 and the 2 match out of place) and lets the
    wrong student win, while position-wise it is 0.4 (only '01'
    agree). '01624' vs the true '01627' is 0.8 position-wise (one
    digit off, the single-digit OCR confusion the near-match branch
    is meant to catch).
    """
    if not a or not b:
        return 0.0
    n = max(len(a), len(b))
    return sum(1 for x, y in zip(a, b) if x == y) / n if n else 0.0


class OCREngine:
    """
    Performs purely dynamic offline recognition of handwritten identification fields.
    Does NOT hardcode student names or roll numbers.
    """


    # Character-to-digit confusion matrix for handwritten digits in printed boxes

    def __init__(self):
        self.ocr = RapidOCR()

    @staticmethod
    def remove_red_color(img_bgr: np.ndarray) -> np.ndarray:
        """
        Precisely removes pre-printed red/pink/brown form lines, boxes, and text.
        Leaves dark student handwriting on pure white background.
        """
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        
        # Red hue wrap-around in HSV: 0-20 and 160-180 with moderate saturation and brightness
        is_red_hsv = ((h < 20) | (h > 160)) & (s > 25) & (v > 80)
        
        # Also check RGB: red component substantially higher than green and blue
        b, g, r = cv2.split(img_bgr)
        is_red_rgb = (r > 115) & (r.astype(int) - g.astype(int) > 15) & (r.astype(int) - b.astype(int) > 15)
        
        red_mask = is_red_hsv | is_red_rgb
        cleaned = img_bgr.copy()
        cleaned[red_mask] = [255, 255, 255]
        return cleaned




    def _reconcile_with_roster(
        self,
        candidate_ht: str,
        candidate_name: str,
        raw_ht: str,
        roster: List[Dict[str, str]],
        secondary_roll: Optional[str] = None,
        preferred_prefix: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Dual-signal fuzzy matching against an imported examination roster.
        Co-verifies Hall Ticket (including full prefix & roll digits) and Candidate Name.
        Resolves collisions when multiple students share identical roll suffixes.
        Supports windowed root-name matching and initial expansion for Indian names.
        """
        from difflib import SequenceMatcher
        best_match = None
        best_score = 0.0

        cand_name_upper = candidate_name.upper().strip()
        cand_ht_upper = candidate_ht.upper().strip()
        clean_raw_ht = re.sub(r'[^A-Z0-9]', '', raw_ht.upper())
        sec_roll_u = secondary_roll.upper().strip() if secondary_roll else ""

        clean_name = re.sub(r'^[I\|\!\s]+', '', cand_name_upper).strip()
        c_parts = clean_name.split()
        name_nospace = re.sub(r'\s+', '', clean_name)

        # A hall ticket always has digits. A candidate with no digit
        # at all (a garbled read like 'TAL' from the 50Q grand-test
        # sheet) counts as absent: it must not poison a good name
        # match through the dual-signal combination below. With no
        # usable HT the name-only path runs instead.
        has_cand_ht = bool(cand_ht_upper and cand_ht_upper != "00000"
                           and any(c.isdigit() for c in cand_ht_upper))
        has_cand_name = bool(len(clean_name) >= 3)

        # Extract district prefix for scoped search partitioning (Pillar 2)
        pref_dist = ""
        if preferred_prefix:
            m_dist = re.match(r'^[A-Z]+', preferred_prefix.strip())
            if m_dist:
                pref_dist = m_dist.group(0)

        for record in roster:
            r_roll = record.get("roll", "").upper().strip()
            r_name = record.get("name", "").upper().strip()
            r_parts = r_name.split()
            rn_nospace = re.sub(r'\s+', '', r_name)

            # A roster row with a roll number but no name must not win
            # on a fuzzy hall-ticket match: a garbled read can be
            # "near" a nameless row and steal the record (348819:
            # 'KKD2025K7300694' matched 'KKD2025KTS00645', blank name).
            # A nameless row may only match on an exact hall ticket.
            if not r_name and has_cand_name:
                exact_ht = bool(
                    r_roll and has_cand_ht
                    and (cand_ht_upper == r_roll
                         or (clean_raw_ht and clean_raw_ht == r_roll)))
                if not exact_ht:
                    continue

            # --- Dimension 1: Hall Ticket Matching Score (0.0 to 1.0) ---
            ht_score = 0.0
            if r_roll and has_cand_ht:
                if cand_ht_upper == r_roll or (clean_raw_ht and clean_raw_ht == r_roll):
                    ht_score = 1.0
                else:
                    s1 = SequenceMatcher(None, cand_ht_upper, r_roll).ratio()
                    s2 = SequenceMatcher(None, clean_raw_ht, r_roll).ratio() if clean_raw_ht else 0.0
                    full_sim = max(s1, s2)

                    # Extract roll numbers (last 3-5 digits)
                    d_cand = re.findall(r'\d+', cand_ht_upper or clean_raw_ht)
                    d_roster = re.findall(r'\d+', r_roll)
                    d_sec = re.findall(r'\d+', sec_roll_u) if sec_roll_u else []

                    digits_match = False
                    d_near_match = False
                    d_sim = 0.0
                    if d_roster:
                        r_digs = d_roster[-1][-5:].zfill(5)
                        c_digs = d_cand[-1][-5:].zfill(5) if d_cand else ""
                        s_digs = d_sec[-1][-5:].zfill(5) if d_sec else ""
                        if (c_digs and c_digs == r_digs) or (s_digs and s_digs == r_digs):
                            digits_match = True
                        else:
                            # Position-wise digit agreement (see
                            # _digit_agreement): roll digits must agree
                            # in position, not merely appear somewhere.
                            sim_c = _digit_agreement(c_digs, r_digs) if c_digs else 0.0
                            sim_s = _digit_agreement(s_digs, r_digs) if s_digs else 0.0
                            d_sim = max(sim_c, sim_s)
                            if d_sim >= 0.80:
                                d_near_match = True

                    # Extract prefix part (everything before the digits)
                    p_cand = re.sub(r'\d+$', '', cand_ht_upper or clean_raw_ht)
                    p_roster = re.sub(r'\d+$', '', r_roll)
                    p_sim = SequenceMatcher(None, p_cand, p_roster).ratio() if (p_cand and p_roster) else 0.0

                    if digits_match:
                        # Digits match: score is heavily scaled by how well the prefix matches!
                        ht_score = max(full_sim, 0.45 + 0.50 * p_sim)
                    elif d_near_match and p_sim >= 0.80:
                        # Near-matching roll digits (e.g. single digit OCR handwriting confusion) with matching prefix
                        ht_score = max(full_sim * 0.90, 0.40 + 0.45 * p_sim + 0.15 * d_sim)
                    else:
                        # Non-matching roll digits: heavily penalize HT score to prevent name fuzzy-matching from hijacking rolls
                        ht_score = min(full_sim * 0.35, 0.30)

            # --- Dimension 2: Candidate Name Matching Score (0.0 to 1.0) ---
            # Pillar 4: Windowed root-name matching, initial-expansion aliasing, and cursive OCR tolerance
            name_score = 0.0
            if r_name and has_cand_name:
                s1 = SequenceMatcher(None, clean_name, r_name).ratio()
                s2 = SequenceMatcher(None, name_nospace, rn_nospace).ratio()
                s3 = SequenceMatcher(None, cand_name_upper, r_name).ratio()
                c_sorted = " ".join(sorted(c_parts))
                r_sorted = " ".join(sorted(r_parts))
                s_sort = SequenceMatcher(None, c_sorted, r_sorted).ratio()
                base_sim = max(s1, s2, s3, s_sort)

                # Check Indian Name order independence (Initial(s) + Given Name vs Given Name + Initial(s))
                c_inits = set(w for w in c_parts if len(w) <= 2)
                c_names = [w for w in c_parts if len(w) > 2]
                r_inits = set(w for w in r_parts if len(w) <= 2)
                r_names = [w for w in r_parts if len(w) > 2]
                
                inits_match = (c_inits == r_inits) if (c_inits and r_inits) else False
                if inits_match and c_names and r_names:
                    c_str = " ".join(c_names)
                    r_str = " ".join(r_names)
                    gn_sim = SequenceMatcher(None, c_str, r_str).ratio()
                    if gn_sim >= 0.80:
                        name_score = max(base_sim, 0.90 + gn_sim * 0.09)

                if set(c_parts) == set(r_parts) and len(c_parts) >= 2:
                    name_score = 1.0

                if name_score == 0.0:
                    # Initial check (e.g. 'B' matches 'B' or 'BANGI')
                    initial_match = False
                    if c_parts and r_parts and c_parts[0][0] == r_parts[0][0]:
                        initial_match = True
                    elif name_nospace and rn_nospace and name_nospace[0] == rn_nospace[0]:
                        initial_match = True

                    main_c = c_parts[-1] if c_parts else name_nospace
                    main_r = r_parts[-1] if r_parts else rn_nospace

                    # Ligature & cursive character normalization (e.g. 'EVRL' / 'OEVR' vs 'DEVI')
                    sub_c = re.sub(r'OE', 'D', main_c)
                    sub_c = re.sub(r'[RL]$', 'I', sub_c)
                    main_sim = max(
                        SequenceMatcher(None, main_c, main_r).ratio(),
                        SequenceMatcher(None, sub_c, main_r).ratio()
                    )

                    # If candidate was extracted as a single continuous token (e.g. 'BOEVR') and roster has initial + name:
                    if len(c_parts) <= 1 and initial_match and len(r_parts) >= 2:
                        rem_c = name_nospace[1:]
                        sub_rem = re.sub(r'OE', 'D', rem_c)
                        sub_rem = re.sub(r'[RL]$', 'I', sub_rem)
                        rem_sim = max(
                            SequenceMatcher(None, rem_c, main_r).ratio(),
                            SequenceMatcher(None, sub_rem, main_r).ratio()
                        )
                        main_sim = max(main_sim, rem_sim)

                    # Windowed root-name search for long given names (>= 8 chars, e.g. 'MALLIKARJUNA')
                    long_r_words = [w for w in r_parts if len(w) >= 8]
                    best_long_sim = 0.0
                    for rw in long_r_words:
                        len_rw = len(rw)
                        for w in range(max(4, len_rw - 3), min(len(name_nospace) + 1, len_rw + 4)):
                            for i in range(len(name_nospace) - w + 1):
                                sub = name_nospace[i:i+w]
                                sim = SequenceMatcher(None, sub, rw).ratio()
                                if sim > best_long_sim:
                                    best_long_sim = sim

                    is_multi = len(c_parts) > 2 or len(r_parts) > 2
                    mid_sim = 0.0
                    if is_multi:
                        c_mid = " ".join(c_parts[1:-1])
                        r_mid = " ".join(r_parts[1:-1])
                        mid_sim = SequenceMatcher(None, c_mid, r_mid).ratio() if (c_mid and r_mid) else 0.0

                    if initial_match and main_sim >= 0.65 and (not is_multi or mid_sim >= 0.50):
                        # Direct or ligature-normalized given name match (e.g. 'B EVRL' / 'BOEVR' vs 'B DEVI')
                        name_score = max(base_sim, 0.85 + main_sim * 0.14)
                    elif initial_match and best_long_sim >= 0.65 and (not is_multi or mid_sim >= 0.50 or base_sim >= 0.60):
                        # Long given name windowed match (e.g. 'MALLIKARJUNA' in 'BAUNIC LUNAMAZLIKAA')
                        name_score = max(base_sim, 0.75 + best_long_sim * 0.22)
                    elif main_sim < 0.50 and len(c_parts) >= 2 and len(r_parts) >= 2 and base_sim < 0.60:
                        # Sharing initial but totally different given name -> penalize
                        name_score = base_sim * 0.40
                    else:
                        name_score = base_sim

            # Pillar 2: Center/District Scoped Search affinity
            dist_bonus = 0.0
            if has_cand_ht and pref_dist and r_roll.startswith(pref_dist):
                dist_bonus = 0.02

            # --- Dimension 3: Dual-Signal Weighted Combination ---
            if has_cand_ht and r_roll and has_cand_name and r_name:
                if ht_score >= 0.98 and name_score >= 0.50:
                    total_score = 1.0
                elif ht_score >= 0.98 and name_score < 0.35:
                    # HT matches exactly but Name is completely different student -> penalize collision!
                    total_score = 0.45 * ht_score + 0.55 * name_score
                elif ht_score >= 0.85 and name_score >= 0.70:
                    total_score = max(0.98, 0.55 * ht_score + 0.45 * name_score)
                else:
                    total_score = 0.60 * ht_score + 0.40 * name_score
            elif has_cand_ht and r_roll:
                if has_cand_name:
                    total_score = ht_score * 0.85
                else:
                    total_score = ht_score
            elif has_cand_name and r_name:
                total_score = name_score
            else:
                total_score = 0.0

            total_score += dist_bonus

            if total_score > best_score:
                best_score = total_score
                best_match = record

        if best_match and best_score >= 0.65:
            return best_match.get("roll"), best_match.get("name")
        return None, None

    def resolve_identity_vote(self, dyn_ht, dyn_name, second_ht,
                              roster=None, preferred_prefix=None):
        """Pick between the dynamic reading and a second dynamic
        reading of the same hall-ticket row.

        Both readings come from the same detected box row: the
        primary read uses the row as found, the second read uses a
        taller strip (read_box_row_strip with expand_bottom=0.25)
        that catches handwriting dipping below the row. They can
        disagree (348819: primary 'KKD2025K7300694', second
        'KKD2025KTS01624'; the sheet says KKD2025KTS01627). When
        they disagree, the roster decides: the reading whose hall
        ticket leads to a roster student whose NAME matches the
        sheet's own (primary) name read wins. A win needs a strong
        name match (>= 0.70): the second reading on 388773 leads to
        'GUDIPALLI RAKESH', whose name only scores 0.64 against the
        sheet's 'GRUDRAKSHI', so it is rejected and the primary
        reading stands. Without a roster, or when neither reading
        matches a roster student, the primary reading stands.

        Returns (ht, name, source) with source "dynamic" or
        "second". The returned hall ticket / name are the
        roster-reconciled values when the roster matched, else the
        raw reading.
        """
        from difflib import SequenceMatcher

        dyn_ht = (dyn_ht or "").strip()
        dyn_name = (dyn_name or "").strip()
        second_ht = (second_ht or "").strip()

        def _name_sim(a, b):
            a = re.sub(r"\s+", "", (a or "").upper())
            b = re.sub(r"\s+", "", (b or "").upper())
            if not a or not b:
                return 0.0
            return SequenceMatcher(None, a, b).ratio()

        def _reconciled(cand_ht):
            if not roster or (not cand_ht and not dyn_name):
                return (None, None)
            try:
                return self._reconcile_with_roster(
                    cand_ht, dyn_name, cand_ht, roster,
                    preferred_prefix=preferred_prefix)
            except Exception:
                return (None, None)

        def _win_score(rec):
            """How strongly this reading matches a roster student
            whose name matches the sheet's own name read (0.0 = no
            win). The name is the primary read for both legs: it is
            the trusted name, and the vote only chooses between the
            two hall-ticket readings."""
            r_ht, r_name = rec
            if not r_ht or not r_name:
                return 0.0
            if not dyn_name:
                # No name on the sheet: only an exact HT match counts.
                return 1.0 if r_ht == dyn_ht or r_ht == second_ht else 0.0
            sim = _name_sim(dyn_name, r_name)
            return sim if sim >= 0.70 else 0.0

        dyn_rec = _reconciled(dyn_ht)
        second_rec = _reconciled(second_ht)
        dyn_score = _win_score(dyn_rec)
        second_score = _win_score(second_rec)
        # A reconciliation is only trusted when the roster student's
        # name matches the sheet's own name read strongly (the 0.70
        # gate inside _win_score). The reconciler can match a garbled
        # hall ticket to the wrong student (348819: the primary read
        # reconciles to 'KKD2025KTS00364', DANDU TARUN KUMAR, whose
        # name only scores 0.56 against the sheet's 'CHANTKUMAG').
        # An untrusted reconciliation falls back to the raw reading —
        # a garbled hall ticket is honest, a wrong student is not.
        dyn_final = ((dyn_rec[0] or dyn_ht, dyn_rec[1] or dyn_name)
                     if dyn_score > 0 else (dyn_ht, dyn_name))
        second_final = ((second_rec[0] or second_ht,
                         second_rec[1] or dyn_name)
                        if second_score > 0 else (second_ht, dyn_name))

        if dyn_ht and second_ht and dyn_ht == second_ht:
            return dyn_final[0], dyn_final[1], "dynamic"
        if dyn_ht and not second_ht:
            return dyn_final[0], dyn_final[1], "dynamic"
        if second_ht and not dyn_ht:
            # Primary found a name but no hall ticket: the name-only
            # reconciliation may already have found the student.
            if dyn_score > 0:
                return dyn_final[0], dyn_final[1], "dynamic"
            if second_score > 0:
                return second_final[0], second_final[1], "second"
            return dyn_final[0], dyn_final[1], "dynamic"
        if not dyn_ht and not second_ht:
            return dyn_final[0], dyn_final[1], "dynamic"

        if second_score > dyn_score:
            return second_final[0], second_final[1], "second"
        return dyn_final[0], dyn_final[1], "dynamic"




# Global OCR engine instance
ocr_engine = OCREngine()
