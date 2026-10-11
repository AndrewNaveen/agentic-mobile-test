"""Deterministic validation of every model-planned action."""

from __future__ import annotations

from .contracts import ActionKind, Observation, PlannedAction, Scenario, StepRecord


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
        scenario: Scenario,
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
        if action.kind in {ActionKind.TAP, ActionKind.TYPE_TEXT}:
            if not action.target_ref:
                raise PolicyViolation(f"{action.kind.value} requires target_ref")
            target = observation.element(action.target_ref)
            if target is None:
                raise PolicyViolation(f"Unknown target reference: {action.target_ref}")
            if not target.enabled:
                raise PolicyViolation(f"Target {action.target_ref} is disabled")
            if not target.executable:
                raise PolicyViolation(f"Target {action.target_ref} has no safe locator")
        elif action.target_ref is not None:
            raise PolicyViolation(f"{action.kind.value} cannot include target_ref")

        if action.kind is ActionKind.TAP and target is not None and not target.clickable:
            raise PolicyViolation(f"Target {action.target_ref} is not reported as clickable")

        if action.kind is ActionKind.TYPE_TEXT:
            if not action.value_ref or action.value_ref not in scenario.test_data:
                raise PolicyViolation("type_text requires an approved test-data reference")
        elif action.value_ref is not None:
            raise PolicyViolation(f"{action.kind.value} cannot include value_ref")

        repeated = 0
        for step in reversed(history):
            ineffective = step.before.fingerprint == step.after.fingerprint
            if step.action.signature() != action.signature() or not ineffective:
                break
            repeated += 1
        if repeated >= self.max_same_ineffective_actions:
            raise PolicyViolation(
                "The planner repeated the same ineffective action too many times"
            )
