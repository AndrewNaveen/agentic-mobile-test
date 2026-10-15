"""Reviewed replay of discovery 20261015T065141.819053Z (c7cb4534).

Generated from its discovered-path.json; launch is normalized to Settings root
so a previously open subpage cannot change the starting navigation.
"""

from pathlib import Path
from typing import Any

import pytest

from agentic_mobile_test.appium.observer import AppiumObserver
from agentic_mobile_test.contracts import Scenario, VerificationState
from agentic_mobile_test.verification.verifier import TextVerifier

SCENARIO_PATH = Path(__file__).parent / "scenarios/artemis_accessibility_helper_enabled.json"


@pytest.mark.appium
def test_artemis_accessibility_helper_enabled(android_settings_environment: Any) -> None:
    """Replay the reviewed path and assert the fixed scenario oracle."""
    # Arrange: the UI fixture reads this scenario's start/cleanup checkpoints.
    scenario = Scenario.load(SCENARIO_PATH)
    device = android_settings_environment.device

    # Act: replay reviewed semantic actions, never captured ephemeral refs.
    device.settings.launch_root()
    device.ui.scroll_until_visible(
        "settings.accessibility", direction="up", max_swipes=8,
    )
    device.ui.tap(
        "settings.accessibility",
        expected_target_id="settings.artemis_accessibility_helper",
        timeout_seconds=10,
    )
    device.ui.tap("settings.artemis_accessibility_helper", timeout_seconds=10)

    # Assert: the same deterministic oracle used during discovery decides the result.
    final_observation = AppiumObserver(device.actions).observe()
    verification = TextVerifier().evaluate(scenario, final_observation)
    assert verification.state is VerificationState.PASSED, verification.summary
