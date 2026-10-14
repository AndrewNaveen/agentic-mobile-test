"""Deterministic baseline journey for the first Android scenario."""

from __future__ import annotations

from typing import Any

import pytest
from appium.webdriver.common.appiumby import AppiumBy

from agentic_mobile_test.device.platform import DeviceConnectivity

SETTINGS_PACKAGE = "com.android.settings"


@pytest.mark.appium
def test_open_android_settings_about_phone(
    android_settings_environment: Any,
) -> None:
    """Open About phone and verify destination content, not merely a successful tap."""

    device = android_settings_environment.device
    evidence_dir = android_settings_environment.evidence_dir
    assert device.profile.is_android
    assert device.platform.settings_app_id == SETTINGS_PACKAGE
    assert device.driver.current_package == SETTINGS_PACKAGE, (
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


@pytest.mark.appium
def test_youtube_offline_retry_waits_until_actionable(
    android_settings_environment: Any,
) -> None:
    """Wait for YouTube's delayed Retry control, tap it, and verify offline state."""

    device = android_settings_environment.device
    youtube_app_id = "com.google.android.youtube"
    assert device.apps.is_installed(youtube_app_id), "YouTube must be installed"

    original_connectivity = device.network.get_connectivity()
    retry_locator = (
        AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().textMatches("(?i)^retry$")',
    )
    offline_message_locator = (
        AppiumBy.ID,
        "com.google.android.youtube:id/error_message_text",
    )
    try:
        device.network.set_connectivity(
            DeviceConnectivity(
                wifi_enabled=False,
                mobile_data_enabled=True,
                airplane_mode_enabled=False,
            )
        )
        device.network.set_airplane_mode(True)
        device.apps.launch(youtube_app_id)

        retry_visible = device.actions.wait_until_visible(
            retry_locator,
            timeout_seconds=60,
        )
        if not retry_visible:
            device.actions.capture_state("youtube-retry-not-visible-after-60-seconds")
        assert retry_visible, "YouTube did not show Retry within 60 seconds"
        assert device.actions.wait_until_clickable(
            retry_locator,
            timeout_seconds=10,
        ), "YouTube showed Retry but it did not become clickable"
        device.actions.tap(retry_locator, timeout_seconds=10)
        assert device.actions.wait_until_visible(
            offline_message_locator,
            timeout_seconds=15,
        ), "The offline message did not return after tapping Retry"
        device.actions.capture_state("youtube-offline-after-retry")
    finally:
        device.network.set_connectivity(original_connectivity)
