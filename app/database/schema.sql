-- Schema for Offline OMR Evaluation System
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS examinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    total_questions INTEGER NOT NULL DEFAULT 160,
    correct_mark REAL NOT NULL DEFAULT 0.50,
    wrong_mark REAL NOT NULL DEFAULT 0.00,
    unattempted_mark REAL NOT NULL DEFAULT 0.00,
    template_name TEXT NOT NULL DEFAULT 'OMR_AP_DSC_160_V1',
    status TEXT NOT NULL DEFAULT 'DRAFT',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS answer_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL DEFAULT 1,
    version_hash TEXT NOT NULL,
    is_locked INTEGER NOT NULL DEFAULT 0,
    source_file TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(exam_id) REFERENCES examinations(id) ON DELETE CASCADE,
    UNIQUE(exam_id, version_number)
);

CREATE TABLE IF NOT EXISTS answer_key_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    answer_key_id INTEGER NOT NULL,
    question_number INTEGER NOT NULL,
    correct_option TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    FOREIGN KEY(answer_key_id) REFERENCES answer_keys(id) ON DELETE CASCADE,
    UNIQUE(answer_key_id, question_number)
);

CREATE TABLE IF NOT EXISTS processed_sheets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    hall_ticket_ocr TEXT,
    hall_ticket_final TEXT,
    candidate_name_ocr TEXT,
    candidate_name_final TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    review_reason TEXT,
    correct_count INTEGER NOT NULL DEFAULT 0,
    wrong_count INTEGER NOT NULL DEFAULT 0,
    unattempted_count INTEGER NOT NULL DEFAULT 0,
    total_marks REAL NOT NULL DEFAULT 0.00,
    student_rank INTEGER NOT NULL DEFAULT 0,
    skew_angle REAL DEFAULT 0.0,
    processed_at TEXT NOT NULL,
    verified_at TEXT,
    FOREIGN KEY(exam_id) REFERENCES examinations(id) ON DELETE CASCADE,
    UNIQUE(exam_id, file_path)
);

CREATE TABLE IF NOT EXISTS question_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sheet_id INTEGER NOT NULL,
    question_number INTEGER NOT NULL,
    detected_option TEXT NOT NULL,
    correct_option TEXT NOT NULL,
    classification TEXT NOT NULL,
    awarded_marks REAL NOT NULL,
    confidence REAL NOT NULL,
    fill_a REAL,
    fill_b REAL,
    fill_c REAL,
    fill_d REAL,
    is_corrected INTEGER NOT NULL DEFAULT 0,
    corrected_option TEXT,
    FOREIGN KEY(sheet_id) REFERENCES processed_sheets(id) ON DELETE CASCADE,
    UNIQUE(sheet_id, question_number)
);

CREATE TABLE IF NOT EXISTS audit_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sheet_id INTEGER NOT NULL,
    field_type TEXT NOT NULL,
    target_index INTEGER,
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    operator TEXT DEFAULT 'Operator',
    timestamp TEXT NOT NULL,
    FOREIGN KEY(sheet_id) REFERENCES processed_sheets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS export_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    export_path TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    export_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(exam_id) REFERENCES examinations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sheets_exam_status ON processed_sheets(exam_id, status);
CREATE INDEX IF NOT EXISTS idx_sheets_rank ON processed_sheets(exam_id, student_rank);
CREATE INDEX IF NOT EXISTS idx_responses_sheet ON question_responses(sheet_id);

