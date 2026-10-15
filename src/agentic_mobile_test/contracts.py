"""Driver-independent contracts for the bounded agentic test loop."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class ActionKind(StrEnum):
    TAP = "tap"
    TYPE_TEXT = "type_text"
    LAUNCH_APP = "launch_app"
    SCROLL_FORWARD = "scroll_forward"
    SCROLL_BACKWARD = "scroll_backward"
    PRESS_BACK = "press_back"


class TextExpectation(StrEnum):
    VISIBLE = "visible"
    ABSENT = "absent"


@dataclass(frozen=True)
class TextAssertion:
    assertion_id: str
    text: str
    exact: bool = True
    expectation: TextExpectation = TextExpectation.VISIBLE
    checked: bool | None = None
    resource_id: str | None = None

    def __post_init__(self) -> None:
        if not self.assertion_id.strip() or not self.text.strip():
            raise ValueError("Text assertions require an id and non-empty text")
        if not isinstance(self.expectation, TextExpectation):
            raise ValueError("Text expectation must be visible or absent")
        if self.checked is not None:
            if not isinstance(self.checked, bool) or self.expectation is not TextExpectation.VISIBLE:
                raise ValueError("checked requires a boolean and a visible assertion")
        if self.resource_id is not None:
            if not isinstance(self.resource_id, str) or not self.resource_id.strip() or self.checked is None:
                raise ValueError("resource_id requires a non-empty ID and a checked assertion")


@dataclass(frozen=True)
class RequiredInteraction:
    """An interaction that must occur before visible assertions can finish a run."""

    action: ActionKind
    target_text: str
    minimum_count: int = 1

    def __post_init__(self) -> None:
        if self.action not in {ActionKind.TAP, ActionKind.TYPE_TEXT}:
            raise ValueError("Required interactions must target a UI element")
        if not self.target_text.strip():
            raise ValueError("A required interaction needs target text")
        if not 1 <= self.minimum_count <= 10:
            raise ValueError("minimum_count must be between 1 and 10")


class ScenarioType(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    EDGE = "edge"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    goal: str
    assertions: tuple[TextAssertion, ...]
    allowed_actions: frozenset[ActionKind] = field(
        default_factory=lambda: frozenset(ActionKind)
    )
    test_data: Mapping[str, str] = field(default_factory=dict, repr=False)
    launchable_apps: Mapping[str, str] = field(default_factory=dict)
    max_steps: int = 8
    scenario_type: ScenarioType = ScenarioType.POSITIVE
    preconditions: tuple[str, ...] = ()
    cleanup: tuple[str, ...] = ()
    required_interactions: tuple[RequiredInteraction, ...] = ()
    start_screen: str = "settings_root"
    cleanup_screen: str = "settings_root"
    allow_toggle_changes: bool = True

    def __post_init__(self) -> None:
        if self.start_screen not in {"settings_root", "home"} or self.cleanup_screen not in {"settings_root", "home"}:
            raise ValueError("Screen checkpoints must be settings_root or home")
        if not isinstance(self.allow_toggle_changes, bool):
            raise ValueError("allow_toggle_changes must be a boolean")
        if not self.scenario_id.strip() or not self.goal.strip():
            raise ValueError("A scenario requires an id and goal")
        if not self.assertions:
            raise ValueError("A scenario requires at least one independent assertion")
        if not self.allowed_actions:
            raise ValueError("A scenario must allow at least one action")
        if not 1 <= self.max_steps <= 50:
            raise ValueError("max_steps must be between 1 and 50")
        if any(not key.strip() for key in self.test_data):
            raise ValueError("Test-data keys cannot be empty")
        if any(
            not isinstance(ref, str)
            or not ref.strip()
            or not isinstance(app_id, str)
            or not app_id.strip()
            for ref, app_id in self.launchable_apps.items()
        ):
            raise ValueError("launchable_apps must map non-empty references to app IDs")
        if not isinstance(self.scenario_type, ScenarioType):
            raise ValueError("scenario_type must be positive, negative, or edge")
        if any(item.action not in self.allowed_actions for item in self.required_interactions):
            raise ValueError("Every required interaction must be an allowed action")
        if sum(item.minimum_count for item in self.required_interactions) > self.max_steps:
            raise ValueError("max_steps cannot be lower than the required interaction count")
        if any(not item.strip() for item in (*self.preconditions, *self.cleanup)):
            raise ValueError("Scenario preconditions and cleanup entries cannot be empty")

    @classmethod
    def load(cls, path: Path) -> Scenario:
        source = Path(path).resolve()
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except OSError as error:
            raise ValueError(f"Unable to read scenario {source}: {error}") from error
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid scenario JSON in {source}: {error}") from error
        if not isinstance(document, Mapping):
            raise ValueError("A scenario document must be a JSON object")
        return cls.from_mapping(document)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> Scenario:
        required = {
            "schema_version",
            "scenario_id",
            "scenario_type",
            "goal",
            "assertions",
            "preconditions",
            "cleanup",
            "allowed_actions",
            "test_data",
            "max_steps",
        }
        missing = required - set(value)
        unknown = set(value) - required - {"launchable_apps", "required_interactions", "start_screen", "cleanup_screen", "allow_toggle_changes"}
        if missing or unknown:
            raise ValueError(
                f"Scenario keys mismatch; missing={sorted(missing)}, "
                f"unknown={sorted(unknown)}"
            )
        schema_version = value["schema_version"]
        if isinstance(schema_version, bool) or schema_version != 1:
            raise ValueError("Only scenario schema_version 1 is supported")

        try:
            scenario_type = ScenarioType(_required_text(value["scenario_type"], "scenario_type"))
            allowed_actions = frozenset(
                ActionKind(action)
                for action in _string_list(value["allowed_actions"], "allowed_actions")
            )
        except ValueError as error:
            raise ValueError(f"Invalid scenario enum value: {error}") from error

        raw_assertions = value["assertions"]
        if not isinstance(raw_assertions, list) or not raw_assertions:
            raise ValueError("assertions must be a non-empty list")
        assertions = tuple(_parse_assertion(item) for item in raw_assertions)
        raw_test_data = value["test_data"]
        if not isinstance(raw_test_data, Mapping) or any(
            not isinstance(key, str) or not isinstance(item, str)
            for key, item in raw_test_data.items()
        ):
            raise ValueError("test_data must map string names to string values")
        raw_launchable_apps = value.get("launchable_apps", {})
        if not isinstance(raw_launchable_apps, Mapping) or any(
            not isinstance(key, str) or not isinstance(app_id, str)
            for key, app_id in raw_launchable_apps.items()
        ):
            raise ValueError("launchable_apps must map string references to string app IDs")
        max_steps = value["max_steps"]
        if not isinstance(max_steps, int) or isinstance(max_steps, bool):
            raise ValueError("max_steps must be an integer")
        raw_interactions = value.get("required_interactions", [])
        if not isinstance(raw_interactions, list):
            raise ValueError("required_interactions must be a list")
        interactions = tuple(_parse_required_interaction(item) for item in raw_interactions)

        return cls(
            scenario_id=_required_text(value["scenario_id"], "scenario_id"),
            goal=_required_text(value["goal"], "goal"),
            assertions=assertions,
            allowed_actions=allowed_actions,
            test_data=dict(raw_test_data),
            launchable_apps=dict(raw_launchable_apps),
            max_steps=max_steps,
            scenario_type=scenario_type,
            preconditions=tuple(_string_list(value["preconditions"], "preconditions")),
            cleanup=tuple(_string_list(value["cleanup"], "cleanup")),
            required_interactions=interactions,
            start_screen=value.get("start_screen", "settings_root"),
            cleanup_screen=value.get("cleanup_screen", "settings_root"),
            allow_toggle_changes=value.get("allow_toggle_changes", True),
        )


def _parse_required_interaction(value: object) -> RequiredInteraction:
    if not isinstance(value, Mapping) or set(value) - {
        "action",
        "target_text",
        "minimum_count",
    }:
        raise ValueError("A required interaction has invalid fields")
    try:
        action = ActionKind(_required_text(value.get("action"), "interaction action"))
    except ValueError as error:
        raise ValueError(f"Invalid required interaction action: {error}") from error
    target_text = _required_text(value.get("target_text"), "interaction target_text")
    minimum_count = value.get("minimum_count", 1)
    if not isinstance(minimum_count, int) or isinstance(minimum_count, bool):
        raise ValueError("interaction minimum_count must be an integer")
    return RequiredInteraction(action, target_text, minimum_count)


def _parse_assertion(value: object) -> TextAssertion:
    if not isinstance(value, Mapping):
        raise ValueError("Each assertion must be an object")
    allowed = {"assertion_id", "text", "exact", "expectation", "checked", "resource_id"}
    if set(value) - allowed or not {"assertion_id", "text"}.issubset(value):
        raise ValueError(
            "Assertions require assertion_id and text; exact and expectation are optional"
        )
    exact = value.get("exact", True)
    if not isinstance(exact, bool):
        raise ValueError("Assertion exact must be true or false")
    try:
        expectation = TextExpectation(value.get("expectation", TextExpectation.VISIBLE))
    except ValueError as error:
        raise ValueError("Assertion expectation must be visible or absent") from error
    return TextAssertion(
        assertion_id=_required_text(value["assertion_id"], "assertion_id"),
        text=_required_text(value["text"], "assertion text"),
        exact=exact,
        expectation=expectation,
        checked=value.get("checked"),
        resource_id=value.get("resource_id"),
    )


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _string_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of strings")
    return [_required_text(item, name) for item in value]


@dataclass(frozen=True)
class ObservedElement:
    """One UI element exposed to the planner through an opaque reference."""

    ref: str
    label: str
    text: str = ""
    accessibility_id: str = ""
    resource_id: str = ""
    class_name: str = ""
    clickable: bool = False
    enabled: bool = True
    checked: bool | None = None
    toggles_state: bool = False
    checkable: bool = False
    toggle_labels: tuple[str, ...] = ()
    locator_strategy: str | None = field(default=None, repr=False)
    locator_value: str | None = field(default=None, repr=False)

    @property
    def executable(self) -> bool:
        return bool(self.locator_strategy and self.locator_value)


@dataclass(frozen=True)
class Observation:
    sequence: int
    fingerprint: str
    screenshot: Path
    ui_source: Path
    elements: tuple[ObservedElement, ...]
    app_package: str | None = None
    activity: str | None = None

    def element(self, ref: str) -> ObservedElement | None:
        return next((element for element in self.elements if element.ref == ref), None)


@dataclass(frozen=True)
class PlannedAction:
    kind: ActionKind
    reason: str
    expected_effect: str
    target_ref: str | None = None
    value_ref: str | None = None

    def signature(self) -> tuple[str, str | None, str | None]:
        return (
            self.kind.value,
            self.target_ref,
            self.value_ref,
        )


@dataclass(frozen=True)
class ExecutionResult:
    operation: str
    elapsed_seconds: float
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StepRecord:
    step_number: int
    before: Observation
    action: PlannedAction
    execution: ExecutionResult
    after: Observation


class VerificationState(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    PRODUCT_FAILURE = "product_failure"


@dataclass(frozen=True)
class AssertionCheck:
    assertion_id: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class VerificationResult:
    state: VerificationState
    checks: tuple[AssertionCheck, ...]
    summary: str


class RunOutcome(StrEnum):
    PASSED = "passed"
    PRODUCT_FAILURE = "product_failure"
    TEST_FAILURE = "test_failure"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class RunResult:
    scenario_id: str
    outcome: RunOutcome
    summary: str
    steps: tuple[StepRecord, ...]
    final_verification: VerificationResult | None
    run_directory: Path | None = None
