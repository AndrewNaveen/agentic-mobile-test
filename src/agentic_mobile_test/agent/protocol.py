"""Shared parsing and errors for model-selected actions."""
from typing import Any, Mapping
from ..contracts import ActionKind, PlannedAction

class PlannerResponseError(ValueError):
    """Invalid model response."""

class ModelGatewayUnavailableError(RuntimeError):
    """Provider or local budget unavailable."""

class ModelBudgetExhaustedError(ModelGatewayUnavailableError):
    """Local call or estimated-cost limit prevents another request."""

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
