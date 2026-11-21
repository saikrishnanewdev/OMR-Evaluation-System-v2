"""Main application entry point for the Offline OMR Evaluation System desktop client."""
import sys
import os
import traceback
import ctypes
from pathlib import Path

# Ensure application root and bundle directory are on sys.path
if getattr(sys, 'frozen', False):
    APP_ROOT = Path(sys.executable).parent
    BUNDLE_DIR = Path(getattr(sys, '_MEIPASS', APP_ROOT))
    # When frozen, BUNDLE_DIR contains all compiled modules and MUST be first in sys.path
    # to prevent loose external .py files in APP_ROOT from shadowing bundled code
    if str(BUNDLE_DIR) not in sys.path:
        sys.path.insert(0, str(BUNDLE_DIR))
    if str(APP_ROOT) not in sys.path:
        sys.path.append(str(APP_ROOT))
else:
    APP_ROOT = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = APP_ROOT
    if str(APP_ROOT) not in sys.path:
        sys.path.insert(0, str(APP_ROOT))

# Safe working directory anchoring
try:
    if APP_ROOT.exists():
        os.chdir(str(APP_ROOT))
except Exception:
    pass


def log_fatal_exception(exc_type, exc_val, exc_tb):
    """Logs fatal crashes to disk and displays a native Windows message box so the app never vanishes silently."""
    err_msg = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
    
    # 1. Write crash log to disk
    crash_paths = [
        APP_ROOT / "crash.log",
        Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "OMREvaluationSystem" / "crash.log"
    ]
    saved_path = None
    for cp in crash_paths:
        try:
            cp.parent.mkdir(parents=True, exist_ok=True)
            with open(cp, "w", encoding="utf-8") as f:
                f.write(f"=== OMR Evaluation System Crash Log ===\n")
                f.write(f"Executable: {sys.executable}\n")
                f.write(f"Bundle Dir: {getattr(sys, '_MEIPASS', 'N/A')}\n")
                f.write(f"Current Dir: {os.getcwd()}\n\n")
                f.write(err_msg)
            saved_path = cp
            break
        except Exception:
            pass

    user_notice = (
        f"A startup error occurred:\n\n{exc_val}\n\n"
        f"A detailed error log has been saved to:\n{saved_path if saved_path else 'Application directory'}"
    )

    # 2. Try native Windows MessageBox (works even if PySide6 completely failed)
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(0, user_notice, "OMR Evaluation System Error", 0x10)
        except Exception:
            pass

    # 3. Print to stderr if console is attached
    if sys.stderr is not None:
        try:
            print(f"\n[FATAL ERROR] {user_notice}\n", file=sys.stderr)
            print(err_msg, file=sys.stderr)
        except Exception:
            pass


sys.excepthook = log_fatal_exception

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon, QFont, QPalette, QColor
from PySide6.QtCore import Qt
from app.database.connection import db_manager


def apply_dark_theme(app: QApplication) -> None:
    """Applies a professional modern dark Windows desktop color palette."""
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(35, 35, 35))
    palette.setColor(QPalette.ToolTipBase, QColor(220, 220, 220))
    palette.setColor(QPalette.ToolTipText, QColor(30, 30, 30))
    palette.setColor(QPalette.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.Button, QColor(45, 45, 48))
    palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Link, QColor(0, 120, 215))
    palette.setColor(QPalette.Highlight, QColor(0, 120, 215))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    font = QFont("Segoe UI", 10)
    app.setFont(font)


def main():
    try:
        if "--check" in sys.argv:
            print("=== OMR Evaluation System v1.0.0 Diagnostic Check ===")
            db_manager.init_schema()
            print("[OK] Database schema initialized.")
            from app.evaluation.answer_key import AnswerKeyExtractor
            extractor = AnswerKeyExtractor()
            print(f"[OK] Digit templates loaded: {list(extractor.templates.keys())}")
            from app.ocr.engine import OCREngine
            ocr = OCREngine()
            print("[OK] RapidOCR engine initialized.")
            print("[SUCCESS] All system core components verified.")
            sys.exit(0)

        # Windows high DPI attributes
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

        app = QApplication(sys.argv)
        app.setApplicationName("Offline OMR Evaluation System")
        app.setOrganizationName("Syam Evaluation Systems")

        apply_dark_theme(app)

        # Initialize SQLite database
        db_manager.init_schema()

        if "--advanced" in sys.argv:
            from app.ui.main_window import MainWindow
            window = MainWindow()
        else:
            from app.ui.client_window import ClientWindow
            window = ClientWindow()
        window.show()

        sys.exit(app.exec())
    except Exception as e:
        log_fatal_exception(*sys.exc_info())
        sys.exit(1)


if __name__ == "__main__":
    main()
