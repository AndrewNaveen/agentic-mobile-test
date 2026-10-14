"""Deterministic replay of the offline path discovered with Gemini."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentic_mobile_test.appium.observer import AppiumObserver
from agentic_mobile_test.contracts import Scenario, VerificationState
from agentic_mobile_test.device.platform import DeviceConnectivity
from agentic_mobile_test.verification.verifier import TextVerifier

SCENARIO_PATH = Path(__file__).parent / "scenarios/youtube_airplane_mode_offline.json"


@pytest.mark.appium
def test_youtube_airplane_mode_offline(
    android_settings_environment: Any,
) -> None:
    """Replay Gemini's reviewed path and verify YouTube's deterministic offline copy."""

    scenario = Scenario.load(SCENARIO_PATH)
    device = android_settings_environment.device
    original = device.network.get_connectivity()
    online_baseline = DeviceConnectivity(
        wifi_enabled=False,
        mobile_data_enabled=True,
        airplane_mode_enabled=False,
    )

    try:
        device.network.set_connectivity(online_baseline)

        # These two semantic taps and the launch were recorded in discovery step order.
        device.ui.tap("settings.network_internet", timeout_seconds=10)
        device.ui.tap("settings.airplane_mode", timeout_seconds=10)
        device.apps.launch(scenario.launchable_apps["youtube"])

        final_observation = AppiumObserver(device.actions).observe()
        verification = TextVerifier().evaluate(scenario, final_observation)
        assert verification.state is VerificationState.PASSED, verification.summary
        device.actions.capture_state("youtube-airplane-mode-offline-verified")
    finally:
        device.network.set_connectivity(original)
        assert device.network.get_connectivity() == original
