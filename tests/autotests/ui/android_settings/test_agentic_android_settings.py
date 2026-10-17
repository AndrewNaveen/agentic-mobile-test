"""Opt-in Gemini-planned, Appium-executed Android Settings journey."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from agentic_mobile_test.appium import AppiumExecutor
from agentic_mobile_test.appium.observer import AppiumObserver
from agentic_mobile_test.contracts import (
    RunOutcome,
    Scenario,
)
from agentic_mobile_test.gateways import GeminiBudget, GeminiGateway
from agentic_mobile_test.device.platform import DeviceConnectivity
from agentic_mobile_test.agent.planner import StructuredPlanner
from agentic_mobile_test.agent.policy import ActionPolicy
from agentic_mobile_test.agent.runner import AgentLoop
from agentic_mobile_test.verification.verifier import TextVerifier

SCENARIO_PATHS = sorted((Path(__file__).with_name("scenarios")).glob("*.json"))
ANDROID_SETTINGS_SCENARIOS = tuple(Scenario.load(path) for path in SCENARIO_PATHS)


@pytest.mark.appium
@pytest.mark.gemini
@pytest.mark.parametrize(
    "scenario",
    ANDROID_SETTINGS_SCENARIOS,
    ids=lambda scenario: scenario.scenario_id,
)
def test_agentic_android_settings_scenario(
    android_settings_environment: Any,
    scenario: Scenario,
) -> None:
    """Let Gemini navigate, but let deterministic code decide the verdict."""

    device = android_settings_environment.device
    evidence_dir = android_settings_environment.evidence_dir
    original_connectivity: DeviceConnectivity | None = None
    result = None
    network_record: dict[str, object] | None = None

    try:
        if scenario.scenario_id == "youtube-airplane-mode-offline":
            youtube_app_id = scenario.launchable_apps["youtube"]
            if not device.apps.is_installed(youtube_app_id):
                pytest.fail(
                    "YouTube is not installed on the connected Android device",
                    pytrace=False,
                )
            original_connectivity = device.network.get_connectivity()
            baseline = DeviceConnectivity(
                wifi_enabled=False,
                mobile_data_enabled=True,
                airplane_mode_enabled=False,
            )
            network_record = {
                "captured_before": _connectivity_record(original_connectivity),
                "test_precondition": _connectivity_record(baseline),
                "restored_after": None,
            }
            _write_network_record(evidence_dir, network_record)
            device.network.set_connectivity(baseline)

        gateway = GeminiGateway.from_environment(
            budget=GeminiBudget(
                max_calls=scenario.max_steps,
                max_output_tokens=100,
                max_cost_usd=Decimal("0.005"),
            )
        )
        loop = AgentLoop(
            planner=StructuredPlanner(gateway),
            observer=AppiumObserver(device.actions),
            policy=ActionPolicy(max_same_ineffective_actions=1),
            executor=AppiumExecutor(device.actions, apps=device.apps),
            verifier=TextVerifier(),
        )

        result = loop.run(scenario, runs_directory=evidence_dir)
        if network_record is not None:
            network_record["after_agent"] = _connectivity_record(
                device.network.get_connectivity()
            )
            _write_network_record(evidence_dir, network_record)
        android_settings_environment.attach_result(result)
    finally:
        if original_connectivity is not None:
            restored = device.network.set_connectivity(original_connectivity)
            observed = _connectivity_record(device.network.get_connectivity())
            if network_record is not None:
                network_record["restored_after"] = observed
                network_record["restore_operation"] = {
                    "name": restored.operation,
                    "elapsed_seconds": restored.elapsed_seconds,
                }
                _write_network_record(evidence_dir, network_record)
            assert observed == _connectivity_record(original_connectivity)

    assert result is not None
    assert result.outcome is RunOutcome.PASSED, result.summary
    assert 1 <= len(result.steps) <= scenario.max_steps
    assert 1 <= gateway.usage.calls <= scenario.max_steps
    assert gateway.usage.estimated_cost_usd <= Decimal("0.005")
    assert result.run_directory is not None
    assert (result.run_directory / "result.json").is_file()
    assert (result.run_directory / "navigation-path.json").is_file()
    assert (result.run_directory / "lifecycle.json").is_file()
    if scenario.scenario_id == "youtube-airplane-mode-offline":
        assert network_record is not None
        assert network_record["captured_before"] == network_record["restored_after"]
        assert network_record["after_agent"]["airplane_mode_enabled"] is True
        assert network_record["after_agent"]["wifi_enabled"] is False


def _connectivity_record(state: DeviceConnectivity) -> dict[str, bool]:
    return {
        "wifi_enabled": state.wifi_enabled,
        "mobile_data_enabled": state.mobile_data_enabled,
        "airplane_mode_enabled": state.airplane_mode_enabled,
    }


def _write_network_record(
    evidence_dir: Path,
    record: dict[str, object],
) -> None:
    path = evidence_dir / "network-lifecycle.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
