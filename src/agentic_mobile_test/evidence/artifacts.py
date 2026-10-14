"""Local, redacted evidence for an agentic scenario run."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any
from uuid import uuid4

from ..contracts import Observation, RunOutcome, RunResult, Scenario, StepRecord

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_.-]+")


class RunArtifacts:
    def __init__(self, run_directory: Path, scenario: Scenario) -> None:
        self.run_directory = run_directory
        self.scenario = scenario
        self._steps_path = run_directory / "steps.jsonl"

    @classmethod
    def create(cls, root: Path, scenario: Scenario) -> RunArtifacts:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        safe_id = _SAFE_NAME.sub("-", scenario.scenario_id).strip("-") or "scenario"
        run_directory = root / f"{timestamp}-{safe_id}-{uuid4().hex[:8]}"
        run_directory.mkdir(parents=True, exist_ok=False)
        artifacts = cls(run_directory, scenario)
        artifacts._write_json(
            run_directory / "scenario.json",
            _scenario_record(scenario),
        )
        return artifacts

    def record_step(self, step: StepRecord) -> None:
        with self._steps_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(_jsonable(step), sort_keys=True) + "\n")

    def finish(self, result: RunResult) -> None:
        self._write_json(self.run_directory / "result.json", result)
        if result.outcome is RunOutcome.PASSED:
            self._write_json(
                self.run_directory / "discovered-path.json",
                _discovered_path(self.run_directory, self.scenario, result),
            )

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.write_text(
            json.dumps(_jsonable(value), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        converted = [_jsonable(item) for item in value]
        return sorted(converted) if isinstance(value, (set, frozenset)) else converted
    return value


def _scenario_record(scenario: Scenario) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "scenario_id": scenario.scenario_id,
        "scenario_type": scenario.scenario_type.value,
        "goal": scenario.goal,
        "preconditions": scenario.preconditions,
        "cleanup": scenario.cleanup,
        "assertions": scenario.assertions,
        "allowed_actions": scenario.allowed_actions,
        "launchable_apps": scenario.launchable_apps,
        "test_data_refs": sorted(scenario.test_data),
        "max_steps": scenario.max_steps,
    }


def _discovered_path(
    run_directory: Path,
    scenario: Scenario,
    result: RunResult,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "record_type": "successful_ui_path",
        "generation_status": "candidate_requires_review",
        "scenario": _scenario_record(scenario),
        "steps": [_discovered_step(run_directory, step) for step in result.steps],
        "verification": result.final_verification,
    }


def _discovered_step(run_directory: Path, step: StepRecord) -> dict[str, Any]:
    observed_target = (
        step.before.element(step.action.target_ref)
        if step.action.target_ref is not None
        else None
    )
    target_record = None
    if observed_target is not None:
        target_record = {
            "observed_ref": observed_target.ref,
            "label": observed_target.label,
            "text": observed_target.text,
            "accessibility_id": observed_target.accessibility_id,
            "resource_id": observed_target.resource_id,
            "class_name": observed_target.class_name,
            "locator_candidate": (
                {
                    "strategy": observed_target.locator_strategy,
                    "value": observed_target.locator_value,
                }
                if observed_target.executable
                else None
            ),
        }
    return {
        "sequence": step.step_number,
        "action": {
            "name": step.action.kind.value,
            "target": target_record,
            "value_ref": step.action.value_ref,
        },
        "planning": {
            "reason": step.action.reason,
            "expected_effect": step.action.expected_effect,
        },
        "execution": {
            "operation": step.execution.operation,
            "elapsed_seconds": step.execution.elapsed_seconds,
        },
        "transition": {
            "screen_changed": step.before.fingerprint != step.after.fingerprint,
            "before": _observation_evidence(
                run_directory,
                step.before,
                f"step-{step.step_number:04d}-before",
            ),
            "after": _observation_evidence(
                run_directory,
                step.after,
                f"step-{step.step_number:04d}-after",
            ),
        },
    }


def _observation_evidence(
    run_directory: Path,
    observation: Observation,
    label: str,
) -> dict[str, Any]:
    evidence_directory = run_directory / "evidence"
    evidence_directory.mkdir(exist_ok=True)
    screenshot = _stage_evidence(
        observation.screenshot,
        evidence_directory / f"{label}.png",
    )
    ui_source = _stage_evidence(
        observation.ui_source,
        evidence_directory / f"{label}.xml",
    )
    return {
        "fingerprint": observation.fingerprint,
        "app_package": observation.app_package,
        "activity": observation.activity,
        "screenshot": os.path.relpath(screenshot, run_directory),
        "screenshot_sha256": _file_sha256(screenshot),
        "ui_source": os.path.relpath(ui_source, run_directory),
        "ui_source_sha256": _file_sha256(ui_source),
    }


def _stage_evidence(source: Path, destination: Path) -> Path:
    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Discovery evidence is missing: {source}")
    shutil.copy2(source, destination)
    return destination


def _file_sha256(path: Path) -> str | None:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
