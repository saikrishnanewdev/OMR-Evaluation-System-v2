"""
Cryptographic License & Trial Management Module
===============================================
Features:
  1. Unique Hardware Machine ID: Derives a persistent machine fingerprint based on Windows GUID / MAC.
  2. 3-Day Trial Period: Automatically counts down 3 calendar days (72 hours) from the very first launch.
  3. Tamper Protection: HMAC-SHA256 signature and anti-clock-rollback detection.
  4. Cryptographic Key Verification: Validates machine-locked activation keys.
"""

import os
import sys
import json
import time
import uuid
import hmac
import hashlib
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

# Secret salt for HMAC signing and key generation (keep private)
LICENSE_PEPPER = b"OMR_EVALUATION_SECURE_SALT_2026_X99_DSC_SYS"
TRIAL_DURATION_SECONDS = 3 * 24 * 3600  # 3 days = 259,200 seconds


def get_machine_id() -> str:
    """
    Computes a deterministic, unique, hardware-based Machine ID for this computer.
    Format: OMR-XXXX-XXXX-XXXX
    """
    hw_tokens = []

    # 1. Windows MachineGuid from Registry (most stable on Windows)
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            hw_tokens.append(str(guid).strip())
        except Exception:
            pass

    # 2. Hardware MAC address node
    try:
        node = uuid.getnode()
        hw_tokens.append(f"{node:012X}")
    except Exception:
        pass

    # 3. Environment username & computername as fallback
    comp_name = os.environ.get("COMPUTERNAME", "")
    hw_tokens.append(comp_name)

    raw_combined = "::".join(hw_tokens)
    digest = hashlib.sha256(raw_combined.encode("utf-8")).hexdigest().upper()
    # Format as 3 groups of 4 characters: OMR-XXXX-XXXX-XXXX
    return f"OMR-{digest[0:4]}-{digest[4:8]}-{digest[8:12]}"


def generate_license_key(machine_id: str) -> str:
    """
    Generates the official valid activation key for a given Machine ID.
    Format: XXXX-XXXX-XXXX-XXXX
    """
    norm_mid = machine_id.strip().upper()
    mac = hmac.new(LICENSE_PEPPER, norm_mid.encode("utf-8"), hashlib.sha256).hexdigest().upper()
    return f"{mac[0:4]}-{mac[4:8]}-{mac[8:12]}-{mac[12:16]}"


def verify_license_key(machine_id: str, entered_key: str) -> Tuple[bool, str]:
    """
    Verifies if entered key is valid for this machine.
    Supports machine-specific keys and developer master override keys.
    """
    norm_mid = machine_id.strip().upper()
    clean_entered = entered_key.strip().upper().replace(" ", "").replace("-", "")

    # Universal Developer Master Override
    master_key = "MASTEROMRPRO2026"
    if clean_entered == master_key:
        return True, "Master License Activated"

    expected_key = generate_license_key(norm_mid).replace("-", "")
    if clean_entered == expected_key:
        return True, "Machine License Verified"

    return False, "Invalid activation key for this machine."


class LicenseManager:
    """Manages the 3-day trial lifecycle and license activation persistence."""

    def __init__(self):
        self.machine_id = get_machine_id()
        self.storage_path = self._get_storage_path()
        self._ensure_initialized()

    def _get_storage_path(self) -> Path:
        """Determines secure local application data path."""
        if sys.platform == "win32":
            app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            if app_data:
                base = Path(app_data) / "OMREvaluationSystem"
            else:
                base = Path.home() / ".omr_system"
        else:
            base = Path.home() / ".omr_system"

        base.mkdir(parents=True, exist_ok=True)
        return base / "license_state.dat"

    def _compute_signature(self, data_dict: Dict[str, Any]) -> str:
        """Generates HMAC signature for license data tampering verification."""
        clean_data = {k: v for k, v in data_dict.items() if k != "signature"}
        serialized = json.dumps(clean_data, sort_keys=True)
        return hmac.new(LICENSE_PEPPER, serialized.encode("utf-8"), hashlib.sha256).hexdigest()

    def _ensure_initialized(self) -> None:
        """Initializes trial record on first run with tamper verification."""
        now = time.time()
        if not self.storage_path.exists():
            payload = {
                "machine_id": self.machine_id,
                "first_run": now,
                "last_run": now,
                "is_activated": False,
                "activation_key": ""
            }
            payload["signature"] = self._compute_signature(payload)
            self._save_payload(payload)

    def _load_payload(self) -> Optional[Dict[str, Any]]:
        """Loads and verifies signature of license state."""
        try:
            if not self.storage_path.exists():
                return None
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            stored_sig = data.get("signature", "")
            expected_sig = self._compute_signature(data)
            if stored_sig != expected_sig:
                # Tampered file!
                return None
            return data
        except Exception:
            return None

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        """Saves payload with fresh signature."""
        try:
            payload["signature"] = self._compute_signature(payload)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            print(f"[LICENSE] Warning: could not write license file: {e}")

    def get_status(self) -> Dict[str, Any]:
        """
        Returns complete license status:
        {
            "status": "ACTIVATED" | "TRIAL" | "EXPIRED" | "TAMPERED",
            "machine_id": str,
            "days_left": int,
            "hours_left": int,
            "is_activated": bool,
            "message": str
        }
        """
        payload = self._load_payload()
        if payload is None:
            # File was deleted or tampered
            now = time.time()
            return {
                "status": "EXPIRED",
                "machine_id": self.machine_id,
                "days_left": 0,
                "hours_left": 0,
                "is_activated": False,
                "message": "License validation error or tampered record. Please activate."
            }

        now = time.time()

        # Check if already activated
        if payload.get("is_activated", False):
            key = payload.get("activation_key", "")
            is_valid, _ = verify_license_key(self.machine_id, key)
            if is_valid:
                return {
                    "status": "ACTIVATED",
                    "machine_id": self.machine_id,
                    "days_left": 9999,
                    "hours_left": 99999,
                    "is_activated": True,
                    "message": "Full License Active (Perpetual)"
                }

        # Check anti-clock rollback
        last_run = payload.get("last_run", 0.0)
        first_run = payload.get("first_run", now)

        if now < last_run - 3600:  # Allowed 1 hour clock skew for timezone/DST
            return {
                "status": "EXPIRED",
                "machine_id": self.machine_id,
                "days_left": 0,
                "hours_left": 0,
                "is_activated": False,
                "message": "System clock rollback detected. Trial expired. Please activate."
            }

        # Update last run time
        payload["last_run"] = now
        self._save_payload(payload)

        # Calculate trial expiration
        elapsed = now - first_run
        if elapsed < TRIAL_DURATION_SECONDS:
            remaining_sec = max(0.0, TRIAL_DURATION_SECONDS - elapsed)
            remaining_hours = int(remaining_sec / 3600)
            remaining_days = max(1, int(remaining_sec / 86400) + (1 if remaining_sec % 86400 > 0 else 0))
            return {
                "status": "TRIAL",
                "machine_id": self.machine_id,
                "days_left": remaining_days,
                "hours_left": remaining_hours,
                "is_activated": False,
                "message": f"Trial Active: {remaining_days} Day(s) Remaining ({remaining_hours} hours)"
            }
        else:
            return {
                "status": "EXPIRED",
                "machine_id": self.machine_id,
                "days_left": 0,
                "hours_left": 0,
                "is_activated": False,
                "message": "3-Day Evaluation Trial has Expired. Please activate."
            }

    def activate(self, key: str) -> Tuple[bool, str]:
        """Validates key and permanently activates software on this machine."""
        is_valid, msg = verify_license_key(self.machine_id, key)
        if not is_valid:
            return False, msg

        payload = self._load_payload() or {
            "machine_id": self.machine_id,
            "first_run": time.time(),
            "last_run": time.time()
        }
        payload["is_activated"] = True
        payload["activation_key"] = key.strip().upper()
        self._save_payload(payload)
        return True, "Software successfully activated! Full license unlocked."


# Global singleton
license_manager = LicenseManager()

