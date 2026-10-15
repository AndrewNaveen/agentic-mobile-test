"""Android Settings-specific pytest fixture and lifecycle evidence."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from agentic_mobile_test.contracts import RunResult, Scenario
from agentic_mobile_test.device import MobileDevice

ANDROID_SETTINGS_PACKAGE = "com.android.settings"
TARGET_CATALOG = Path(__file__).parent / "android_settings/targets/android_settings.json"


@dataclass
class AndroidSettingsEnvironment:
    """Known Settings root checkpoint around one agentic scenario."""

    device: MobileDevice
    evidence_dir: Path
    setup_record: dict[str, Any] | None = None
    cleanup_record: dict[str, Any] | None = None
    result: RunResult | None = None
    start_screen: str = "settings_root"
    cleanup_screen: str = "settings_root"

    def _reach(self, screen: str) -> Any:
        if screen == "home":
            return self.device.go_home()
        operation = self.device.settings.launch_root()
        self._require_settings_package(screen)
        return operation

    def setup(self) -> None:
        try:
            operation = self._reach(self.start_screen)
            self.setup_record = self._checkpoint("ready", operation.operation)
        except Exception as error:
            self.setup_record = _lifecycle_failure(error)
            self._write_lifecycle()
            raise
        self._write_lifecycle()

    def attach_result(self, result: RunResult) -> None:
        self.result = result
        self._write_lifecycle()

    def cleanup(self) -> None:
        try:
            operation = self._reach(self.cleanup_screen)
            self.cleanup_record = self._checkpoint("ready", operation.operation)
        except Exception as error:
            self.cleanup_record = _lifecycle_failure(error)
            self._write_lifecycle()
            raise
        self._write_lifecycle()

    def _require_settings_package(self, phase: str) -> None:
        package = getattr(self.device.driver, "current_package", None)
        if package != ANDROID_SETTINGS_PACKAGE:
            raise RuntimeError(
                f"Android Settings {phase} did not reach the expected package: "
                f"{package!r}"
            )

    def _checkpoint(self, status: str, operation: str) -> dict[str, Any]:
        state = self.device.actions.capture_state(f"fixture-{operation}-ready")
        return {
            "status": status,
            "operation": operation,
            "app_package": getattr(self.device.driver, "current_package", None),
            "activity": getattr(self.device.driver, "current_activity", None),
            "screenshot": str(state.screenshot),
            "ui_source": str(state.ui_source),
            "recorded_at": datetime.now(UTC).isoformat(),
        }

    def _write_lifecycle(self) -> None:
        payload = {
            "schema_version": 1,
            "environment": "android_settings",
            "expected_checkpoint": {"start_screen": self.start_screen, "cleanup_screen": self.cleanup_screen},
            "setup": self.setup_record,
            "cleanup": self.cleanup_record,
            "agent_run": (
                {
                    "scenario_id": self.result.scenario_id,
                    "outcome": self.result.outcome.value,
                    "run_directory": str(self.result.run_directory),
                }
                if self.result is not None
                else None
            ),
        }
        destinations = [self.evidence_dir / "lifecycle.json"]
        if self.result is not None and self.result.run_directory is not None:
            destinations.append(self.result.run_directory / "lifecycle.json")
        for destination in destinations:
            destination.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )


@pytest.fixture
def android_settings_environment(
    driver: Any,
    runs_directory: Path,
    request: pytest.FixtureRequest,
) -> Iterator[AndroidSettingsEnvironment]:
    """Launch and restore Android Settings around agentic navigation."""
    evidence_dir = runs_directory / (
        f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S.%fZ')}"
        f"-android-settings-lifecycle-{uuid4().hex[:8]}"
    )
    evidence_dir.mkdir(parents=True, exist_ok=False)
    device = MobileDevice.create(
        driver,
        evidence_dir=evidence_dir,
        target_catalog=TARGET_CATALOG,
        record_successful_actions=True,
    )
    environment = AndroidSettingsEnvironment(device, evidence_dir)
    if "scenario" in request.fixturenames:
        scenario = request.getfixturevalue("scenario")
    else:
        scenario_path = getattr(request.module, "SCENARIO_PATH", None)
        scenario = Scenario.load(scenario_path) if scenario_path is not None else None
    if isinstance(scenario, Scenario):
        environment.start_screen = scenario.start_screen
        environment.cleanup_screen = scenario.cleanup_screen
    try:
        environment.setup()
        yield environment
    finally:
        environment.cleanup()


def _lifecycle_failure(error: Exception) -> dict[str, str]:
    return {
        "status": "failed",
        "error": f"{type(error).__name__}: {error}",
        "recorded_at": datetime.now(UTC).isoformat(),
    }
