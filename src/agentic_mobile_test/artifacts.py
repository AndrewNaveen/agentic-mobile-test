"""Local, redacted evidence for an agentic scenario run."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from .contracts import RunResult, Scenario, StepRecord

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_.-]+")


class RunArtifacts:
    def __init__(self, run_directory: Path) -> None:
        self.run_directory = run_directory
        self._steps_path = run_directory / "steps.jsonl"

    @classmethod
    def create(cls, root: Path, scenario: Scenario) -> RunArtifacts:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        safe_id = _SAFE_NAME.sub("-", scenario.scenario_id).strip("-") or "scenario"
        run_directory = root / f"{timestamp}-{safe_id}-{uuid4().hex[:8]}"
        run_directory.mkdir(parents=True, exist_ok=False)
        artifacts = cls(run_directory)
        artifacts._write_json(
            run_directory / "scenario.json",
            {
                "scenario_id": scenario.scenario_id,
                "goal": scenario.goal,
                "assertions": scenario.assertions,
                "allowed_actions": scenario.allowed_actions,
                "test_data_refs": sorted(scenario.test_data),
                "max_steps": scenario.max_steps,
            },
        )
        return artifacts

    def record_step(self, step: StepRecord) -> None:
        with self._steps_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(_jsonable(step), sort_keys=True) + "\n")

    def finish(self, result: RunResult) -> None:
        self._write_json(self.run_directory / "result.json", result)

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
