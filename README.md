# Offline OMR Evaluation System for Windows

A production-grade, 100% offline desktop application built for high-throughput, high-accuracy OMR (Optical Mark Recognition) evaluation of standardized examination answer sheets against reference answer-key PDFs.

---

## 1. Key Architectural Features

- **100% Offline Autonomy:** Zero external network calls, zero cloud APIs, zero telemetric tracking. Operates in fully air-gapped secure examination environments.
- **Calibrated Computer Vision Pipeline:** OpenCV-based color separation (`255 - R` red-dropout separation) eliminating red form lines, dual 49-mark timing track registration, and inner-core circular mask sampling.
- **Answer-Key PDF Extraction:** PyMuPDF rasterization at 300 DPI, table grid localization, and Normalized Cross-Correlation (NCC) digit classification with immutable SHA-256 version locking.
- **Candidate Identification:** 16-character segmented box extraction for Hall Ticket Numbers with RapidOCR offline neural inference and candidate name fallback.
- **Dynamic mode (no layout):** `app/omr/dynamic.py` finds hall ticket and name without any fixed coordinates — it locates the "Hall Ticket Number" / "Name of the Candidate" label, then reads the boxes on that same horizontal line. Bubbles are found the same way: each row starts with a question number, then 4 circles on that line, found inside the pink answer columns detected on the sheet itself. The key PDF only sets the expected question count (200 / 160 / 150 / 50 / 20). `EvaluationService` tries dynamic first and falls back to the fixed 160Q/200Q templates when dynamic cannot find enough of the sheet.
- **Deterministic Evaluation & Ranking:** Exact decimal scoring arithmetic and Standard Competition Ranking (1224 rules: $1, 2, 2, 4\dots$) matching state examination guidelines.
- **Interactive Manual Review Workspace:** Dual-pane pan/zoom canvas with colored bubble overlays, candidate info editing, and auditable manual corrections that instantly recalculate batch scores and ranks.
- **Certified Excel Output:** Microsoft Excel (`.xlsx`) generation matching the reference column schema (`File`, `Hall Ticket Number/Name`, `Correct`, `Correct Marks`, `Wrong`, `Unattempted`, `Student Rank`) with automated post-generation openpyxl validation.
- **ACID Relational Storage:** Embedded SQLite 3 database with WAL mode and live backup/restore.

---

## 2. Directory Structure

```
Application/
├── app/
│   ├── main.py                  # Desktop application entry point & Qt app lifecycle
│   ├── config/                  # App constants, scoring defaults, paths
│   │   ├── constants.py
│   │   └── settings.py
│   ├── database/                # SQLite persistence, schema migrations, repositories
│   │   ├── connection.py        # Connection pooling, WAL mode, backup/restore
│   │   ├── schema.sql           # DDL schema definition
│   │   └── repository.py        # Typed CRUD and dashboard query routines
│   ├── omr/                     # Computer vision & bubble detection engine
│   │   ├── preprocessor.py      # Registration marks, skew correction, color dropout
│   │   └── dynamic.py           # Dynamic extraction: labels, box rows & bubbles found on the sheet
│   ├── ocr/                     # Offline OCR & candidate identification pipeline
│   │   └── engine.py            # RapidOCR offline engine with roster reconciliation
│   ├── evaluation/              # Deterministic scoring, ranking, tie-breaking
│   │   ├── answer_key.py        # PDF table extraction, validation, immutability
│   │   ├── scoring_engine.py    # Configurable scoring arithmetic & mark policies
│   │   └── ranking_engine.py    # Competition ranking (1224) & audit flags
│   ├── export/                  # Excel workbook generation & programmatic validation
│   │   ├── excel_exporter.py    # openpyxl formatted exporter
│   │   └── excel_validator.py   # Automated post-generation verification
│   ├── models/                  # Domain dataclasses & typed entities
│   │   └── entities.py
│   ├── services/                # Application coordination & threading
│   │   ├── evaluation_service.py# End-to-end evaluation orchestrator
│   │   └── batch_service.py     # Multi-file batch queue & worker thread
│   └── ui/                      # PySide6 desktop views, widgets, dialogues
│       ├── main_window.py       # Main shell with sidebar navigation & status bar
│       ├── views/
│       │   ├── dashboard_view.py
│       │   ├── exam_setup_view.py
│       │   ├── answer_key_view.py
│       │   ├── batch_import_view.py
│       │   ├── manual_review_view.py
│       │   ├── results_view.py
│       │   └── export_view.py
│       └── widgets/
│           └── image_viewer.py   # Pan/zoom interactive image canvas with overlays
├── data/                        # Local SQLite database (omr_evaluation.db)
├── models/                      # Offline OCR & template weights (template_digits.npz)
├── logs/                        # Rotating application logs
├── tests/                       # Comprehensive automated test suite
│   ├── conftest.py
│   ├── synthetic_generator.py   # High-fidelity synthetic OMR generator
│   ├── test_reconciliation.py   # 100% ground-truth verification
│   └── test_all_scenarios.py    # Full coverage of the 18 mandatory test scenarios
├── OMR_325601.jpg               # Reference scanned sheet
├── SA-08.pdf                    # Reference answer key
├── KNL SA.xls                   # Ground-truth reference Excel register
├── requirements.txt             # Pinned dependency manifest
├── run_app.bat                  # One-click Windows launch script
├── run_tests.bat                # One-click Windows test script
├── omr_evaluator.spec           # PyInstaller build configuration
├── PROJECT_ANALYSIS.md          # Technical analysis report
├── ANSWER_KEY_ANALYSIS.md       # PDF key extraction & validation specification
└── TESTING_STRATEGY.md          # Verification, synthetic test & QA methodology
```

---

## 3. Installation & Quick Start

### 3.1 Prerequisites
- Microsoft Windows 10 or Windows 11 (64-bit).
- Python 3.10+ (Tested on Python 3.13.2 64-bit).

### 3.2 Setup Virtual Environment & Install Dependencies
Open PowerShell or Command Prompt in the project folder:
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3.3 Launch the Application
Double-click `run_app.bat` or execute:
```powershell
python app/main.py
```

### 3.4 Run the Automated Test Suite
Double-click `run_tests.bat` or execute:
```powershell
python -m pytest -v tests/
```

---

## 4. End-to-End Operator Workflow

### Step 1: Examination Setup
1. Navigate to the **Examination Setup** tab.
2. Enter the **Examination Code** (e.g. `AP_DSC_SA08`) and **Examination Name**.
3. Configure the scoring rules:
   - **Questions:** `160`
   - **Correct Mark:** `+0.50`
   - **Wrong Mark Deduction:** `0.00`
   - **Unattempted Mark:** `0.00`
4. Select the reference PDF (`SA-08.pdf`) and click **"Extract & Validate PDF Key"**.
5. Click **"Save & Activate Examination"**.

### Step 2: Answer Key Verification & Locking
1. Switch to the **Answer Key** tab.
2. Review the 160 extracted answers arranged in 4 columns of 40 rows.
3. If necessary, click any cell to edit an answer.
4. Click **"Approve & Lock Key"** to certify the key and generate its immutable SHA-256 hash.

### Step 3: Batch Ingestion & Processing
1. Switch to the **Batch Processing** tab.
2. Click **"Add Scanned Files..."** or **"Import Complete Folder..."** to select scanned OMR sheets.
3. Click **"Start Batch Processing"**.
4. The background worker evaluates sheets without UI freezing, updating real-time progress.

### Step 4: Manual Review Workspace
1. Switch to the **Manual Review** tab.
2. Select any sheet flagged with `[REVIEW_REQUIRED]`.
3. The interactive viewer displays the original sheet with green overlays on correct answers, red on wrong answers, and yellow on ambiguous/multi-marks.
4. Correct any candidate details (Hall Ticket Number or Name) or question answers.
5. Click **"Apply Correction & Recalculate"** to update total marks and ranks immediately.

### Step 5: Results Inspection & Ranking
1. Switch to the **Results & Ranking** tab.
2. Filter candidates by status or search by Hall Ticket or Name.
3. Verify that scores and competition ranks (1, 2, 2, 4...) conform to examination standards.

### Step 6: Certified Excel Export & Automated Audit
1. Switch to the **Export to Excel** tab.
2. Select the destination file path.
3. Click **"Generate & Validate Excel Workbook"**.
4. The application generates the `.xlsx` file, programmatically re-opens it via `openpyxl`, and validates every row against database records before displaying the certification confirmation.

---

## 5. Ground-Truth Verification Benchmark

The application was validated against the reference files `OMR_325601.jpg`, `SA-08.pdf`, and `KNL SA.xls`:

| Parameter | Evaluated by Application | Ground Truth (`KNL SA.xls`) | Validation Result |
|---|:---:|:---:|:---:|
| **Total Questions** | 160 | 160 | **100% Match** |
| **Correct Answers** | 107 | 107 | **100% Match** |
| **Wrong Answers** | 53 | 53 | **100% Match** |
| **Unattempted** | 0 | 0 | **100% Match** |
| **Total Marks** | 53.50 | 53.50 | **100% Match** |
| **Hall Ticket** | `KNL2025SATS00001` | `KNL2025SATS00001` | **100% Match** |
| **Student Rank** | 1 | 1 | **100% Match** |

---

## 6. Building the Windows Standalone Executable

To build a standalone portable executable that runs without Python:
```powershell
pyinstaller omr_evaluator.spec
```
The compiled application and its offline assets will be located in `dist/OMREvaluationSystem/`.

---

## 7. Database Backup & Restore

- **Live Online Backup:** In the application sidebar, click **"Backup Database..."** to create a zero-downtime point-in-time copy of `data/omr_evaluation.db`.
- **Safe Restore:** Click **"Restore Database..."** to restore from any valid backup file after an automated SQLite integrity check.

