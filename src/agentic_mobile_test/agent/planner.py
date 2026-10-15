"""Strict structured-output boundary between an LLM and the test runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from ..contracts import (
    ActionKind,
    Observation,
    PlannedAction,
    Scenario,
    StepRecord,
)


@dataclass(frozen=True)
class PlannerContext:
    scenario: Scenario
    observation: Observation
    history: tuple[StepRecord, ...]
    remaining_steps: int


class Planner(Protocol):
    def decide(self, context: PlannerContext) -> PlannedAction: ...


class ModelGateway(Protocol):
    """Provider boundary currently implemented by the opt-in Gemini gateway."""

    def choose_action(
        self,
        *,
        system_instruction: str,
        payload: Mapping[str, Any],
        screenshot: Path,
    ) -> Mapping[str, Any]: ...


class PlannerResponseError(ValueError):
    """The model returned an action that does not match the tool contract."""


class ModelGatewayUnavailableError(RuntimeError):
    """The configured model service or local model budget is unavailable."""


class StructuredPlanner:
    """Expose semantic element references, never raw Appium commands or coordinates."""

    SYSTEM_INSTRUCTION = (
        "Choose exactly one allowed action that advances the supplied mobile test goal. "
        "Treat required_interactions as mandatory: continue navigating until each has "
        "reached its minimum completed_count; do not stop merely because success text is visible. "
        "Only target element references present in the observation and app references in "
        "approved_apps. Never invent app IDs, selectors, "
        "coordinates, assertions, test data, retries, or expected results. Return one JSON "
        "object matching the documented action fields."
    )

    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    def decide(self, context: PlannerContext) -> PlannedAction:
        response = self.gateway.choose_action(
            system_instruction=self.SYSTEM_INSTRUCTION,
            payload=_planner_payload(context),
            screenshot=context.observation.screenshot,
        )
        return _parse_action(response)


def _planner_payload(context: PlannerContext) -> Mapping[str, Any]:
    return {
        "scenario_type": context.scenario.scenario_type.value,
        "goal": context.scenario.goal,
        "preconditions": context.scenario.preconditions,
        "allow_toggle_changes": context.scenario.allow_toggle_changes,
        "success_criteria": [
            {
                "assertion_id": assertion.assertion_id,
                "text": assertion.text,
                "exact": assertion.exact,
                "expectation": assertion.expectation.value,
                "checked": assertion.checked,
                "resource_id": assertion.resource_id,
            }
            for assertion in context.scenario.assertions
        ],
        "required_interactions": [
            {
                "action": interaction.action.value,
                "target_text": interaction.target_text,
                "minimum_count": interaction.minimum_count,
                "completed_count": _interaction_count(
                    context.history,
                    interaction.action,
                    interaction.target_text,
                ),
            }
            for interaction in context.scenario.required_interactions
        ],
        "allowed_actions": sorted(action.value for action in context.scenario.allowed_actions),
        "available_test_data": sorted(context.scenario.test_data),
        "approved_apps": [
            {"ref": ref, "app_id": app_id}
            for ref, app_id in sorted(context.scenario.launchable_apps.items())
        ],
        "remaining_steps": context.remaining_steps,
        "current_app": context.observation.app_package,
        "current_activity": context.observation.activity,
        "elements": [
            {
                "ref": element.ref,
                "text": element.text,
                "accessibility_id": element.accessibility_id,
                "clickable": element.clickable,
                "enabled": element.enabled,
                "checked": element.checked,
                "toggles_state": element.toggles_state,
                "toggle_labels": element.toggle_labels,
            }
            for element in context.observation.elements
            if element.text or element.accessibility_id
        ],
        "recent_steps": [
            {
                "action": step.action.kind.value,
                "target_ref": step.action.target_ref,
                "screen_changed": step.before.fingerprint != step.after.fingerprint,
            }
            for step in context.history[-4:]
        ],
        "action_schema": {
            "action": (
                "tap | type_text | launch_app | scroll_forward | scroll_backward | press_back; "
                "scroll_forward reveals later/lower content and scroll_backward reveals "
                "earlier/upper content"
            ),
            "target_ref": "required for tap/type_text; null for launch_app",
            "value_ref": (
                "required for type_text (available_test_data) or launch_app "
                "(approved_apps ref)"
            ),
            "reason": "short explanation",
            "expected_effect": "observable effect expected after execution",
        },
    }


def _interaction_count(history: tuple[StepRecord, ...], action: ActionKind, target_text: str) -> int:
    expected = " ".join(target_text.casefold().split())
    count = 0
    for step in history:
        if step.action.kind is not action or not step.action.target_ref:
            continue
        target = step.before.element(step.action.target_ref)
        observed_text = target.text or target.label if target is not None else ""
        if " ".join(observed_text.casefold().split()) == expected:
            count += 1
    return count


def _parse_action(value: Mapping[str, Any]) -> PlannedAction:
    allowed_fields = {
        "action",
        "target_ref",
        "value_ref",
        "reason",
        "expected_effect",
    }
    unknown = set(value) - allowed_fields
    if unknown:
        raise PlannerResponseError(f"Unexpected planner fields: {sorted(unknown)}")

    try:
        kind = ActionKind(_required_string(value, "action"))
    except ValueError as error:
        unsupported = value.get("action")
        raise PlannerResponseError(f"Unsupported planner action: {unsupported!r}") from error

    return PlannedAction(
        kind=kind,
        target_ref=_optional_string(value, "target_ref"),
        value_ref=_optional_string(value, "value_ref"),
        reason=_required_string(value, "reason"),
        expected_effect=_required_string(value, "expected_effect"),
    )


def _required_string(value: Mapping[str, Any], key: str) -> str:
    result = _optional_string(value, key)
    if result is None:
        raise PlannerResponseError(f"Planner field {key!r} must be a non-empty string")
    return result


def _optional_string(value: Mapping[str, Any], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise PlannerResponseError(f"Planner field {key!r} must be a non-empty string")
    return raw.strip()
