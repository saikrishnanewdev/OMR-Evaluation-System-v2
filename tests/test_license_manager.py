"""
Unit tests for License and 3-Day Trial Management
=================================================
"""

import time
import pytest
from app.security.license_manager import (
    get_machine_id, generate_license_key, verify_license_key,
    LicenseManager, TRIAL_DURATION_SECONDS
)


def test_machine_id_format():
    mid = get_machine_id()
    assert mid.startswith("OMR-")
    parts = mid.split("-")
    assert len(parts) == 4
    for p in parts[1:]:
        assert len(p) == 4


def test_generate_and_verify_license_key():
    mid = "OMR-1234-5678-9ABC"
    key = generate_license_key(mid)
    assert len(key.replace("-", "")) == 16

    # Valid key check
    valid, msg = verify_license_key(mid, key)
    assert valid is True

    # Invalid key check
    valid_bad, msg_bad = verify_license_key(mid, "AAAA-BBBB-CCCC-DDDD")
    assert valid_bad is False

    # Key from different machine rejected
    other_mid = "OMR-9999-8888-7777"
    valid_other, _ = verify_license_key(other_mid, key)
    assert valid_other is False


def test_master_key_verification():
    mid = get_machine_id()
    valid, msg = verify_license_key(mid, "MASTEROMRPRO2026")
    assert valid is True

    valid_dash, msg_dash = verify_license_key(mid, "MASTER-OMR-PRO-2026")
    assert valid_dash is True


def test_trial_lifecycle(tmp_path):
    mgr = LicenseManager()
    mgr.storage_path = tmp_path / "test_license.dat"
    mgr._ensure_initialized()

    status = mgr.get_status()
    assert status["status"] in ("TRIAL", "ACTIVATED")
    if not status["is_activated"]:
        assert status["days_left"] <= 3

    # Test activation
    key = generate_license_key(mgr.machine_id)
    success, msg = mgr.activate(key)
    assert success is True

    post_status = mgr.get_status()
    assert post_status["status"] == "ACTIVATED"
    assert post_status["is_activated"] is True

