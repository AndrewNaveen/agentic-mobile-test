"""Shared parsing and errors for model-selected actions."""
from typing import Any, Mapping
from math import isfinite
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
        "target_percent",
        "start_percent",
        "end_percent",
    }
    unknown = set(value) - allowed_fields
    if unknown:
        raise PlannerResponseError(f"Unexpected planner fields: {sorted(unknown)}")

    try:
        kind = ActionKind(_required_string(value, "action"))
    except ValueError as error:
        unsupported = value.get("action")
        raise PlannerResponseError(f"Unsupported planner action: {unsupported!r}") from error

    target_percent = value.get("target_percent")
    if kind is ActionKind.SET_SLIDER_VALUE:
        if (type(target_percent) not in {int, float} or not 0 <= target_percent <= 100
                or not isfinite(target_percent)):
            raise PlannerResponseError("set_slider_value requires a numeric target_percent from 0 to 100")
    elif target_percent is not None:
        raise PlannerResponseError("Only set_slider_value accepts target_percent")

    start_percent, end_percent = value.get("start_percent"), value.get("end_percent")
    if kind is ActionKind.DRAG_SLIDER:
        if any(type(x) not in {int, float} or not 0 <= x <= 100 or not isfinite(x)
               for x in (start_percent, end_percent)):
            raise PlannerResponseError("drag_slider requires start_percent and end_percent from 0 to 100")
        if not 1 <= abs(end_percent - start_percent) <= 30:
            raise PlannerResponseError("drag_slider must span 1 to 30 percentage points")
    elif start_percent is not None or end_percent is not None:
        raise PlannerResponseError("Only drag_slider accepts start_percent and end_percent")

    return PlannedAction(
        kind=kind,
        target_ref=_optional_string(value, "target_ref"),
        value_ref=_optional_string(value, "value_ref"),
        reason=_required_string(value, "reason"),
        expected_effect=_required_string(value, "expected_effect"),
        target_percent=target_percent,
        start_percent=start_percent,
        end_percent=end_percent,
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
