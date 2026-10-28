"""Driver-independent contracts for the bounded agentic test loop."""

from __future__ import annotations

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
    SET_SLIDER_VALUE = "set_slider_value"
    DRAG_SLIDER = "drag_slider"


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
    is_slider: bool = False
    slider_value_hint: str = ""

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
    compact_xml: str = ""

    def element(self, ref: str) -> ObservedElement | None:
        return next((element for element in self.elements if element.ref == ref), None)


@dataclass(frozen=True)
class PlannedAction:
    kind: ActionKind
    reason: str
    expected_effect: str
    target_ref: str | None = None
    value_ref: str | None = None
    target_percent: float | None = None
    start_percent: float | None = None
    end_percent: float | None = None

    def signature(self) -> tuple[str, str | None, str | None, float | None, float | None, float | None]:
        return (
            self.kind.value,
            self.target_ref,
            self.value_ref,
            self.target_percent,
            self.start_percent,
            self.end_percent,
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
