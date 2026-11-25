"""Application constants and default configuration parameters."""
from pathlib import Path
import os
import sys

# Base Application Directories
if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle
    APP_ROOT = Path(sys.executable).parent
    BUNDLE_DIR = Path(getattr(sys, '_MEIPASS', APP_ROOT))
else:
    # Running in development
    APP_ROOT = Path(__file__).resolve().parent.parent.parent
    BUNDLE_DIR = APP_ROOT

# Fallback writable directory if executable directory is read-only
local_app_data = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "OMREvaluationSystem"

try:
    DATA_DIR = APP_ROOT / "data"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _test = DATA_DIR / ".write_test"
    _test.touch()
    _test.unlink()
except Exception:
    DATA_DIR = local_app_data / "data"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

try:
    LOGS_DIR = APP_ROOT / "logs"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    LOGS_DIR = local_app_data / "logs"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

MODELS_DIR = (BUNDLE_DIR / "models") if (BUNDLE_DIR / "models").exists() else (APP_ROOT / "models")
try:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

try:
    EXPORTS_DIR = APP_ROOT / "exports"
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    EXPORTS_DIR = local_app_data / "exports"
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DB_PATH = DATA_DIR / "omr_evaluation.db"
DEFAULT_LOG_PATH = LOGS_DIR / "application.log"

# Reference Form Geometry (OMR_AP_DSC_160_V1)
REF_CANVAS_WIDTH = 1644
REF_CANVAS_HEIGHT = 2272

# Dual Timing Tracks
LEFT_TRACK_X_MIN = 80
LEFT_TRACK_X_MAX = 130
RIGHT_TRACK_X_MIN = 1460
RIGHT_TRACK_X_MAX = 1530

# Identification Field Coordinates
HT_FIELD_Y_START = 217
HT_FIELD_Y_END = 253
HT_FIELD_X_START = 464
HT_FIELD_X_END = 1091
HT_NUM_BOXES = 16
HT_BOX_PITCH = 39.18
HT_BOX_INNER_W = 30
HT_BOX_INNER_H = 32

NAME_FIELD_Y_START = 255
NAME_FIELD_Y_END = 305
NAME_FIELD_X_START = 464
NAME_FIELD_X_END = 1091

# Answer Bubble Grid Geometry (160 Questions Standard)
TOTAL_QUESTIONS = 160
QUESTIONS_PER_COLUMN = 40
NUM_COLUMNS = 4
OPTIONS_PER_QUESTION = 4
OPTION_NAMES = ("A", "B", "C", "D")

COLUMN_BASE_X = (274.0, 628.0, 982.0, 1336.0)
OPTION_PITCH_X = 34.0
ROW_BASE_Y = 1076.5
ROW_PITCH_Y = 27.7179

BUBBLE_RADIUS = 11
BUBBLE_CORE_RADIUS_RATIO = 0.75

# Fill Classification Thresholds
FILL_MARKED_THRESHOLD = 60.0
FILL_BLANK_THRESHOLD = 45.0
FILL_RATIO_MIN = 2.0
FILL_AMBIGUOUS_MAX_RATIO = 2.2

# Answer Key PDF Rendering
PDF_RENDER_DPI = 300

# Scoring Defaults
DEFAULT_CORRECT_MARK = 0.50
DEFAULT_WRONG_MARK = 0.00
DEFAULT_UNATTEMPTED_MARK = 0.00

