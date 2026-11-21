# Comprehensive Testing Strategy & Quality Assurance Plan

**Document Version:** 1.0  
**Test Framework:** `pytest` 9.1.1  
**Target Platform:** Windows 10/11 Desktop  
**Coverage Objective:** 100% of mathematical scoring rules, alignment edge cases, and output formatting  

---

## 1. Testing Philosophy & Verification Principles

The evaluation of student examinations carries direct consequences for candidates. Therefore, this system rejects any reliance on superficial mocks or uncalibrated thresholds:
1. **Mathematical Determinism:** $100\%$ reproducible arithmetic using integer centimarks (half-marks represented as integers) to prevent IEEE 754 floating-point inaccuracies.
2. **Ground-Truth Calibration:** Algorithms are calibrated against historical real scans and validated against verified ground-truth examination registers (`KNL SA.xls`).
3. **Synthetic Edge Case Rigor:** Controlled perturbations (rotation, faint pencil, double marking, salt-and-pepper noise, gaussian blur, crop offsets) are programmatically generated to stress-test the vision pipeline under adverse scanning conditions.
4. **Zero Silent Guessing:** When an identification field or bubble is ambiguous, the system must produce an audit flag and require operator confirmation rather than guessing.

---

## 2. Test Architecture & Automated Suite

```
tests/
├── conftest.py                   # Pytest fixtures, test databases, template singletons
├── test_reconciliation.py        # 100% reconciliation of OMR_325601.jpg against KNL SA.xls
├── test_omr_alignment.py         # Timing mark detection, rotation correction, coordinate warp
├── test_bubble_detector.py       # Multi-signal density, inner core masking, fill classification
├── test_student_ocr.py           # 16-box character extraction, color dropout, name fallback
├── test_answer_key_pdf.py        # PDF rendering, table localization, NCC glyph matching
├── test_scoring_ranking.py       # Arithmetic checks, mark rules, competition ranking (1224)
├── test_excel_export.py          # openpyxl workbook creation and programmatic roundtrip audit
├── test_database_persistence.py  # SQLite schema, transactions, migrations, foreign keys
├── test_synthetic_scenarios.py   # Full coverage of the 18 mandatory test scenarios
└── synthetic_generator.py        # Programmatic OMR sheet generator with ground-truth labels
```

---

## 3. Mandatory Test Scenarios & Verification Matrix

The test suite explicitly implements and verifies all 18 mandatory operational scenarios:

| # | Scenario Description | Test Implementation | Expected Verification Criteria |
|:---:|---|---|---|
| **1** | **Clear, fully marked sheet** | Evaluate `OMR_325601.jpg` against `SA-08.pdf` key | Exact match: 107 correct, 53 wrong, 0 unattempted, 53.50 marks. |
| **2** | **All responses blank** | Synthetically generated blank sheet (no filled bubbles) | 0 correct, 0 wrong, 160 unattempted, 0.00 marks. |
| **3** | **Faint pencil / pen marks** | Synthetic bubbles with mean density in range $[48, 58]$ | Flagged as `AMBIGUOUS` / low confidence; operator review required. |
| **4** | **Multiple marked bubbles** | Sheet with 2 or more options filled on questions | Classified as `MULTI`, scored 0.00, highlighted in review screen. |
| **5** | **Partially filled bubbles** | Bubbles with only 30% fill or off-center marks | Evaluated via inner core mask; classified accurately or queued for review. |
| **6** | **Rotated / skewed scan** | Sheet rotated by $+1.5^\circ$, $+3.0^\circ$, $-2.0^\circ$ | Dual 49-timing track detects angle and restores $0^\circ$ alignment without bubble coordinate loss. |
| **7** | **Low-resolution scan** | Sheet downsampled by 50% ($822 \times 1136$ px) | Resolution normalization scales to reference canvas; alerts operator if below minimum DPI. |
| **8** | **Unreadable Hall Ticket** | Hall ticket boxes obscured by stain / smudge | OCR confidence drops below threshold; flagged for manual review; candidate name fallback invoked. |
| **9** | **Duplicate Hall Ticket** | Two sheets in same batch sharing `KNL2025SATS00001` | Database detects collision; flags duplicate in batch table; alerts operator for resolution. |
| **10** | **Missing answer-key entry** | Key configured with only 159 questions | Validation flags missing Question 160; locks evaluation until resolved. |
| **11** | **Corrected answer key** | Operator corrects Question 40 from B to D | Score recalculation triggers; 104 becomes 107; prior run archived with version hash. |
| **12** | **Student with all correct** | Synthetic sheet with all 160 bubbles matching key | 160 correct, 0 wrong, 0 unattempted, 80.00 marks, Rank 1. |
| **13** | **Student with all incorrect**| Synthetic sheet with all 160 bubbles inverted from key | 0 correct, 160 wrong, 0 unattempted, 0.00 marks. |
| **14** | **Tie between students** | Three students achieving 50.50 marks | Ranks assigned as 2, 2, 2, next student assigned Rank 5 (Competition 1224). |
| **15** | **Failed file in batch** | Corrupted / truncated JPEG placed in 100-file folder | System logs error to DB, skips safely, marks file `FAILED`, continues remaining 99 sheets. |
| **16** | **Batch interrupted / resumed** | Process aborted mid-batch and restarted | SQLite transaction keeps processed records intact; resuming skips processed files. |
| **17** | **Manual correction of response** | Operator changes Question 12 from wrong to correct | Score instantly updates (+0.50 marks); student rank recalculates across batch. |
| **18** | **Excel programmatic validation**| Output `.xlsx` generated and reopened via `openpyxl` | Verifies headers, data types, sorting, decimal precision, and formula reconciliations. |

---

## 4. Synthetic Sheet Generation Framework

To validate error conditions without requiring hundreds of physical sheets, `synthetic_generator.py` creates high-fidelity synthetic OMR scans based on the geometric specification:

```python
class SyntheticOMRGenerator:
    """Generates synthetic OMR sheets with ground-truth coordinate labels."""
    def __init__(self, base_template_path='OMR_325601.jpg'):
        self.template = cv2.imread(base_template_path)
        self.blank_sheet = self._create_pristine_blank_form()

    def generate_candidate_sheet(
        self,
        hall_ticket: str,
        answers: dict[int, str],
        rotation_deg: float = 0.0,
        noise_level: float = 0.0,
        faint_indices: list[int] = None,
        multi_indices: list[int] = None
    ) -> tuple[np.ndarray, dict]:
        """Renders synthetic sheet with specified marks and returns ground truth."""
        ...
```

The generator supports:
- Filling any combination of the 160 questions with options A, B, C, D.
- Injecting double bubbles, erasures, and faint pencil marks.
- Applying affine rotational transforms ($\pm 5.0^\circ$) and translation jitters ($\pm 20$ px).
- Adding Gaussian blur, illumination gradients, and scanner noise.
- Printing synthetic character glyphs into the 16 Hall Ticket boxes.

---

## 5. Excel Export Validation Protocol

Before saving any exported examination workbook, `app/export/excel_validator.py` executes an automated programmatic audit:

1. **Workbook Structure Check:**
   - Worksheet named `"Examination Results"`.
   - Exact column names in exact order:
     1. `File`
     2. `Hall Ticket Number/Name`
     3. `Correct`
     4. `Correct Marks`
     5. `Wrong`
     6. `Unattempted`
     7. `Student Rank`
2. **Data Integrity & Consistency Check:**
   - Every row satisfies: $\text{Correct} + \text{Wrong} + \text{Unattempted} = 160$.
   - $\text{Correct Marks} = \text{Correct} \times 0.50$ (formatted to 2 decimal places).
   - Hall Ticket Number preserved as textual string (preventing scientific notation e.g. `1.23E+10`).
3. **Ranking Monotonicity Check:**
   - Rows sorted in ascending order of `Student Rank`.
   - Tied scores share identical rank.
   - Next rank accounts for ties ($R_{next} = R_{curr} + N_{tied}$).
4. **Database Cross-Validation:**
   - Row count matches database evaluated student count.
   - Every cell value exactly equals the corresponding record in SQLite.

