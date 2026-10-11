"""Opt-in Gemini-planned, Appium-executed Android Settings journey."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from agentic_mobile_test.appium import AppiumExecutor
from agentic_mobile_test.appium.observer import AppiumObserver
from agentic_mobile_test.contracts import (
    ActionKind,
    RunOutcome,
    Scenario,
    VisibleTextAssertion,
)
from agentic_mobile_test.device import MobileDevice
from agentic_mobile_test.gateways import GeminiBudget, GeminiGateway
from agentic_mobile_test.planner import StructuredPlanner
from agentic_mobile_test.policy import ActionPolicy
from agentic_mobile_test.runner import AgentLoop
from agentic_mobile_test.verifier import VisibleTextVerifier

TARGETS_PATH = Path(__file__).with_name("targets") / "android_settings.json"


@pytest.mark.appium
@pytest.mark.gemini
def test_agent_opens_android_settings_about_phone(
    driver: Any,
    runs_directory: Path,
) -> None:
    """Let Gemini navigate, but let deterministic code decide the verdict."""

    evidence_dir = _evidence_directory(runs_directory)
    device = MobileDevice.create(
        driver,
        evidence_dir=evidence_dir,
        target_catalog=TARGETS_PATH,
        record_successful_actions=True,
    )
    device.settings.launch_root()

    gateway = GeminiGateway.from_environment(
        budget=GeminiBudget(
            max_calls=3,
            max_output_tokens=200,
            max_cost_usd=Decimal("0.005"),
        )
    )
    scenario = Scenario(
        scenario_id="agentic-open-android-about-phone",
        goal=(
            "Open the Android Settings About phone or About emulated device screen "
            "so device information is visible"
        ),
        assertions=(VisibleTextAssertion("device-name", "Device name"),),
        allowed_actions=frozenset({ActionKind.TAP, ActionKind.SCROLL_FORWARD}),
        max_steps=3,
    )
    loop = AgentLoop(
        planner=StructuredPlanner(gateway),
        observer=AppiumObserver(device.actions),
        policy=ActionPolicy(max_same_ineffective_actions=1),
        executor=AppiumExecutor(device.actions),
        verifier=VisibleTextVerifier(),
    )

    result = loop.run(scenario, runs_directory=evidence_dir)

    assert result.outcome is RunOutcome.PASSED, result.summary
    assert 1 <= len(result.steps) <= 3
    assert 1 <= gateway.usage.calls <= 3
    assert gateway.usage.estimated_cost_usd <= Decimal("0.005")
    assert result.run_directory is not None
    assert (result.run_directory / "result.json").is_file()


def _evidence_directory(runs_directory: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    path = runs_directory / f"{timestamp}-agentic-android-settings-{uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    return path
