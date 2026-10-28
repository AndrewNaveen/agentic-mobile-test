"""Execute policy-approved agent actions through AppiumActions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .actions import AppiumActions
from ..agent.policy import ActionScope
from ..contracts import (
    ActionKind,
    ExecutionResult,
    Observation,
    PlannedAction,
)

if TYPE_CHECKING:
    from ..device.facade import DeviceApplications


class AppiumExecutor:
    def __init__(
        self,
        actions: AppiumActions,
        *,
        apps: DeviceApplications | None = None,
    ) -> None:
        self.actions = actions
        self.apps = apps

    def execute(
        self,
        scenario: ActionScope,
        action: PlannedAction,
        observation: Observation,
    ) -> ExecutionResult:
        slider_details = {}
        if action.kind is ActionKind.TAP:
            result = self.actions.tap(self._locator(action, observation))
        elif action.kind is ActionKind.DRAG_SLIDER:
            result = self.actions.drag_slider(
                self._locator(action, observation), action.start_percent, action.end_percent,
            )
            slider_details = {"evidence": result.evidence}
        elif action.kind is ActionKind.SET_SLIDER_VALUE:
            slider = self.actions.set_slider_value(
                self._locator(action, observation), action.target_percent,
            )
            result = slider.action
            slider_details = {
                "target_percent": slider.target_percent,
                "ui_percent": slider.ui_percent,
                "independent_percent": slider.independent_percent,
                "attempts": slider.attempts,
            }
        elif action.kind is ActionKind.TYPE_TEXT:
            if action.value_ref is None:
                raise ValueError("A policy-approved type_text action requires value_ref")
            result = self.actions.type_text(
                self._locator(action, observation),
                scenario.test_data[action.value_ref],
            )
        elif action.kind is ActionKind.LAUNCH_APP:
            if action.value_ref is None:
                raise ValueError("A policy-approved launch_app action requires value_ref")
            if self.apps is None:
                raise ValueError("launch_app requires the device applications facade")
            app_id = scenario.launchable_apps[action.value_ref]
            result = self.apps.launch(app_id)
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
            details=dict(result.details, **slider_details),
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
