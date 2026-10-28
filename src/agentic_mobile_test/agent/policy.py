"""Deterministic validation of every model-planned action."""

from __future__ import annotations

from math import isfinite
from typing import Mapping, Protocol

from ..contracts import ActionKind, Observation, PlannedAction, StepRecord


class ActionScope(Protocol):
    """Shared execution permissions; exploration does not need test assertions."""

    max_steps: int
    allowed_actions: frozenset[ActionKind]
    allow_toggle_changes: bool
    test_data: Mapping[str, str]
    launchable_apps: Mapping[str, str]


class PolicyViolation(ValueError):
    """A planned action is outside the approved scenario contract."""


class ActionPolicy:
    def __init__(self, *, max_same_ineffective_actions: int = 2) -> None:
        if max_same_ineffective_actions < 1:
            raise ValueError("max_same_ineffective_actions must be at least one")
        self.max_same_ineffective_actions = max_same_ineffective_actions

    def validate(
        self,
        *,
        scenario: ActionScope,
        action: PlannedAction,
        observation: Observation,
        history: tuple[StepRecord, ...],
        step_number: int,
    ) -> None:
        if step_number > scenario.max_steps:
            raise PolicyViolation("The scenario step budget is exhausted")
        if action.kind not in scenario.allowed_actions:
            raise PolicyViolation(f"Action {action.kind.value!r} is not allowed")

        target = None
        slider_actions = {ActionKind.SET_SLIDER_VALUE, ActionKind.DRAG_SLIDER}
        if action.kind in {ActionKind.TAP, ActionKind.TYPE_TEXT, *slider_actions}:
            if not action.target_ref:
                raise PolicyViolation(f"{action.kind.value} requires target_ref")
            target = observation.element(action.target_ref)
            if target is None:
                raise PolicyViolation(f"Unknown target reference: {action.target_ref}")
            if not scenario.allow_toggle_changes and (target.toggles_state or target.checked is not None):
                raise PolicyViolation("This scenario forbids changing toggle state")
            if not target.enabled:
                raise PolicyViolation(f"Target {action.target_ref} is disabled")
            if not target.executable:
                raise PolicyViolation(f"Target {action.target_ref} has no safe locator")
        elif action.target_ref is not None:
            raise PolicyViolation(f"{action.kind.value} cannot include target_ref")

        if action.kind is ActionKind.TAP and target is not None and not target.clickable:
            raise PolicyViolation(f"Target {action.target_ref} is not reported as clickable")
        if target is not None and target.is_slider and action.kind not in slider_actions:
            raise PolicyViolation("Use an explicitly permitted slider action for sliders")
        if action.kind is ActionKind.SET_SLIDER_VALUE:
            if target is None or not target.is_slider:
                raise PolicyViolation("set_slider_value requires a recognized slider reference")
            if (type(action.target_percent) not in {int, float}
                    or not 0 <= action.target_percent <= 100 or not isfinite(action.target_percent)):
                raise PolicyViolation("Slider target_percent must be a finite number from 0 to 100")
        elif action.target_percent is not None:
            raise PolicyViolation(f"{action.kind.value} cannot include target_percent")

        if action.kind is ActionKind.DRAG_SLIDER:
            if target is None or not target.is_slider:
                raise PolicyViolation("drag_slider requires a recognized slider reference")
            if any(type(x) not in {int, float} or not 0 <= x <= 100 or not isfinite(x)
                   for x in (action.start_percent, action.end_percent)):
                raise PolicyViolation("Drag positions must be finite numbers from 0 to 100")
            if not 1 <= abs(action.end_percent - action.start_percent) <= 30:
                raise PolicyViolation("An experimental drag must span 1 to 30 percentage points")
        elif action.start_percent is not None or action.end_percent is not None:
            raise PolicyViolation(f"{action.kind.value} cannot include drag positions")

        if action.kind is ActionKind.TYPE_TEXT:
            if not action.value_ref or action.value_ref not in scenario.test_data:
                raise PolicyViolation("type_text requires an approved test-data reference")
        elif action.kind is ActionKind.LAUNCH_APP:
            if not action.value_ref or action.value_ref not in scenario.launchable_apps:
                raise PolicyViolation("launch_app requires an approved app reference")
        elif action.value_ref is not None:
            raise PolicyViolation(f"{action.kind.value} cannot include value_ref")

        repeated = 0
        for step in reversed(history):
            if action.kind is ActionKind.DRAG_SLIDER:
                previous = step.before.element(step.action.target_ref)
                if (step.action.kind is not ActionKind.DRAG_SLIDER or previous is None
                        or (previous.locator_strategy, previous.locator_value)
                        != (target.locator_strategy, target.locator_value)
                        or (step.action.start_percent, step.action.end_percent)
                        != (action.start_percent, action.end_percent)):
                    break
            else:
                ineffective = step.before.fingerprint == step.after.fingerprint
                if step.action.signature() != action.signature() or not ineffective:
                    break
            repeated += 1
        repeat_limit = (
            min(2, self.max_same_ineffective_actions)
            if action.kind is ActionKind.DRAG_SLIDER
            else self.max_same_ineffective_actions
        )
        if repeated >= repeat_limit:
            if action.kind is ActionKind.DRAG_SLIDER:
                raise PolicyViolation("The same drag probe was already repeated; choose a different experiment")
            raise PolicyViolation(
                "The planner repeated the same ineffective action too many times"
            )
