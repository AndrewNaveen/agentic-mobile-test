"""Deterministic baseline journey for the first Android scenario."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from agentic_mobile_test.device import MobileDevice

SETTINGS_PACKAGE = "com.android.settings"
TARGETS_PATH = Path(__file__).with_name("targets") / "android_settings.json"


@pytest.mark.appium
def test_open_android_settings_about_phone(
    driver: Any,
    runs_directory: Path,
) -> None:
    """Open About phone and verify destination content, not merely a successful tap."""

    evidence_dir = _evidence_directory(runs_directory)
    device = MobileDevice.create(
        driver,
        evidence_dir=evidence_dir,
        target_catalog=TARGETS_PATH,
        record_successful_actions=True,
    )

    device.settings.launch_root()
    assert device.profile.is_android
    assert device.platform.settings_app_id == SETTINGS_PACKAGE
    assert driver.current_package == SETTINGS_PACKAGE, (
        "This baseline must launch Android Settings. Run it with "
        "--appium-package com.android.settings --appium-activity .Settings"
    )
    assert device.geometry.width > 0
    assert device.geometry.height > 0

    device.ui.scroll_until_visible(
        "settings.about_device",
        direction="up",
        max_swipes=8,
    )
    device.ui.tap(
        "settings.about_device",
        expected_target_id="settings.device_name",
        timeout_seconds=10,
    )

    device_name = device.ui.find(
        "settings.device_name",
        state="visible",
        timeout_seconds=5,
    )
    final_state = device.actions.capture_state("verified-about-phone")

    assert device_name.is_displayed()
    assert final_state.screenshot.is_file()
    assert final_state.ui_source.is_file()
    assert (evidence_dir / "locator-trace.jsonl").is_file()


def _evidence_directory(runs_directory: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    return runs_directory / f"{timestamp}-android-settings-{uuid4().hex[:8]}"
