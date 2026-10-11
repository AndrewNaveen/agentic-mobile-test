"""Driver-independent contracts for the bounded agentic test loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


class ActionKind(StrEnum):
    TAP = "tap"
    TYPE_TEXT = "type_text"
    SCROLL_FORWARD = "scroll_forward"
    SCROLL_BACKWARD = "scroll_backward"
    PRESS_BACK = "press_back"


@dataclass(frozen=True)
class VisibleTextAssertion:
    assertion_id: str
    text: str
    exact: bool = True

    def __post_init__(self) -> None:
        if not self.assertion_id.strip() or not self.text.strip():
            raise ValueError("Visible-text assertions require an id and non-empty text")


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    goal: str
    assertions: tuple[VisibleTextAssertion, ...]
    allowed_actions: frozenset[ActionKind] = field(
        default_factory=lambda: frozenset(ActionKind)
    )
    test_data: Mapping[str, str] = field(default_factory=dict, repr=False)
    max_steps: int = 8

    def __post_init__(self) -> None:
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
