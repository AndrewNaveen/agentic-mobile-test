"""Execute policy-approved agent actions through AppiumActions."""

from __future__ import annotations

from .actions import AppiumActions
from ..contracts import (
    ActionKind,
    ExecutionResult,
    Observation,
    PlannedAction,
    Scenario,
)


class AppiumExecutor:
    def __init__(self, actions: AppiumActions) -> None:
        self.actions = actions

    def execute(
        self,
        scenario: Scenario,
        action: PlannedAction,
        observation: Observation,
    ) -> ExecutionResult:
        if action.kind is ActionKind.TAP:
            result = self.actions.tap(self._locator(action, observation))
        elif action.kind is ActionKind.TYPE_TEXT:
            if action.value_ref is None:
                raise ValueError("A policy-approved type_text action requires value_ref")
            result = self.actions.type_text(
                self._locator(action, observation),
                scenario.test_data[action.value_ref],
            )
        elif action.kind in {
            ActionKind.SCROLL_FORWARD,
            ActionKind.SCROLL_BACKWARD,
        }:
            start, end = _scroll_path(action.kind)
            result = self.actions.swipe_relative(start, end)
        elif action.kind is ActionKind.PRESS_BACK:
            result = self.actions.press_back()
        else:
            raise ValueError(f"Unsupported action: {action.kind}")

        return ExecutionResult(
            operation=result.operation,
            elapsed_seconds=result.elapsed_seconds,
            details=result.details,
        )

    @staticmethod
    def _locator(action: PlannedAction, observation: Observation) -> tuple[str, str]:
        if action.target_ref is None:
            raise ValueError("A target action requires target_ref")
        target = observation.element(action.target_ref)
        if target is None or not target.locator_strategy or not target.locator_value:
            raise ValueError(f"Target {action.target_ref!r} has no executable locator")
        return target.locator_strategy, target.locator_value


def _scroll_path(
    action: ActionKind,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Translate a canonical agent action into a private finger swipe."""

    return {
        ActionKind.SCROLL_FORWARD: ((0.5, 0.8), (0.5, 0.2)),
        ActionKind.SCROLL_BACKWARD: ((0.5, 0.2), (0.5, 0.8)),
    }[action]
