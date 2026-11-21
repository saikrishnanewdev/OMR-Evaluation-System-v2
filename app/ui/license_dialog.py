"""
Modern in-app License Activation Dialog
=======================================
Allows clients to view their unique Machine ID, copy it to clipboard,
and enter an activation key to permanently unlock the software.
"""

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QApplication
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QColor

from app.security.license_manager import license_manager


class LicenseDialog(QDialog):
    """Modern modal dialog for entering software license keys."""

    def __init__(self, parent=None, force_lock=False):
        super().__init__(parent)
        self.force_lock = force_lock
        self.setWindowTitle("Software License Activation")
        self.setFixedSize(480, 360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        if force_lock:
            # Disable close button if license has expired
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

        self._setup_ui()
        self._refresh_state()

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #161B22;
                color: #C9D1D9;
            }
            QLabel {
                color: #C9D1D9;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Title
        title_box = QFrame()
        title_box.setStyleSheet("background-color: #21262D; border-radius: 6px; padding: 6px;")
        tb_layout = QHBoxLayout(title_box)
        tb_layout.setContentsMargins(10, 6, 10, 6)

        self.lbl_title = QLabel("🔑 SOFTWARE LICENSE ACTIVATION")
        self.lbl_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.lbl_title.setStyleSheet("color: #58A6FF;")
        tb_layout.addWidget(self.lbl_title)
        layout.addWidget(title_box)

        # Status / Notice Message
        self.lbl_notice = QLabel("A 3-day evaluation trial is included with this software. Enter your permanent license key below to unlock full lifetime access.")
        self.lbl_notice.setWordWrap(True)
        self.lbl_notice.setStyleSheet("color: #8B949E; font-size: 11px;")
        layout.addWidget(self.lbl_notice)

        # Machine ID Box
        layout.addWidget(QLabel("Your Machine ID (Send this to support for your key):"))
        mid_box = QHBoxLayout()
        mid_box.setSpacing(8)

        self.txt_mid = QLineEdit()
        self.txt_mid.setReadOnly(True)
        self.txt_mid.setText(license_manager.machine_id)
        self.txt_mid.setFont(QFont("Consolas", 11, QFont.Bold))
        self.txt_mid.setStyleSheet("""
            QLineEdit {
                background-color: #0D1117;
                color: #58A6FF;
                border: 1px solid #30363D;
                border-radius: 4px;
                padding: 6px 10px;
            }
        """)
        mid_box.addWidget(self.txt_mid, stretch=1)

        self.btn_copy = QPushButton("📋 Copy ID")
        self.btn_copy.setStyleSheet("""
            QPushButton {
                background-color: #21262D;
                color: #C9D1D9;
                border: 1px solid #30363D;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #30363D; color: #FFFFFF; }
        """)
        self.btn_copy.clicked.connect(self._copy_machine_id)
        mid_box.addWidget(self.btn_copy)
        layout.addLayout(mid_box)

        # License Key Input Box
        layout.addWidget(QLabel("Enter License Key (XXXX-XXXX-XXXX-XXXX):"))
        self.txt_key = QLineEdit()
        self.txt_key.setFont(QFont("Consolas", 12, QFont.Bold))
        self.txt_key.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self.txt_key.setStyleSheet("""
            QLineEdit {
                background-color: #0D1117;
                color: #3FB950;
                border: 1px solid #30363D;
                border-radius: 4px;
                padding: 8px 10px;
                letter-spacing: 1px;
            }
        """)
        self.txt_key.textChanged.connect(lambda t: self.txt_key.setText(t.upper()))
        layout.addWidget(self.txt_key)

        # Feedback Status Label
        self.lbl_feedback = QLabel("")
        self.lbl_feedback.setWordWrap(True)
        self.lbl_feedback.setStyleSheet("font-weight: bold; font-size: 11px;")
        layout.addWidget(self.lbl_feedback)

        layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        if not self.force_lock:
            self.btn_cancel = QPushButton("Continue with Trial")
            self.btn_cancel.setStyleSheet("background-color: #21262D; color: #C9D1D9; border: 1px solid #30363D; padding: 8px 16px; border-radius: 4px;")
            self.btn_cancel.clicked.connect(self.reject)
            btn_layout.addWidget(self.btn_cancel)
        else:
            self.btn_exit = QPushButton("Exit Application")
            self.btn_exit.setStyleSheet("background-color: #21262D; color: #F85149; border: 1px solid #30363D; padding: 8px 16px; border-radius: 4px;")
            self.btn_exit.clicked.connect(lambda: sys.exit(0))
            btn_layout.addWidget(self.btn_exit)

        self.btn_activate = QPushButton("🔓 Activate License")
        self.btn_activate.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: #FFFFFF;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #2EA043; }
        """)
        self.btn_activate.clicked.connect(self._do_activate)
        btn_layout.addWidget(self.btn_activate, stretch=1)

        layout.addLayout(btn_layout)

    def _refresh_state(self):
        info = license_manager.get_status()
        if info["is_activated"]:
            self.lbl_notice.setText("✅ Your software is permanently licensed and active.")
            self.lbl_notice.setStyleSheet("color: #3FB950; font-weight: bold;")
            self.txt_key.setText("ACTIVATED (FULL ACCESS)")
            self.txt_key.setEnabled(False)
            self.btn_activate.setEnabled(False)
        elif info["status"] == "TRIAL":
            self.lbl_notice.setText(f"⏱️ You are currently using the 3-day evaluation trial ({info['days_left']} day(s) remaining).")
            self.lbl_notice.setStyleSheet("color: #D29922;")
        else:
            self.lbl_notice.setText("⚠️ Your 3-day evaluation trial has EXPIRED. Please enter a valid activation key to unlock.")
            self.lbl_notice.setStyleSheet("color: #F85149; font-weight: bold;")

    def _copy_machine_id(self):
        QApplication.clipboard().setText(self.txt_mid.text().strip())
        self.btn_copy.setText("✓ Copied!")
        self.lbl_feedback.setText("Machine ID copied to clipboard. Share it with your administrator to get your key.")
        self.lbl_feedback.setStyleSheet("color: #58A6FF;")

    def _do_activate(self):
        entered = self.txt_key.text().strip()
        if not entered:
            self.lbl_feedback.setText("Please enter an activation key.")
            self.lbl_feedback.setStyleSheet("color: #F85149;")
            return

        success, msg = license_manager.activate(entered)
        if success:
            self.lbl_feedback.setText("🎉 " + msg)
            self.lbl_feedback.setStyleSheet("color: #3FB950; font-size: 12px; font-weight: bold;")
            self.btn_activate.setEnabled(False)
            self.txt_key.setEnabled(False)
            self.accept()
        else:
            self.lbl_feedback.setText("❌ " + msg)
            self.lbl_feedback.setStyleSheet("color: #F85149; font-weight: bold;")

