"""Completion review contracts; model assessments are not product verdicts."""

from .protocol import PlannerResponseError

COMPLETION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["decision", "reason", "gaps", "evidence_screens"],
    "properties": {
        "decision": {"type": "string", "enum": ["complete", "continue", "needs_guidance"]},
        "reason": {"type": "string"},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "evidence_screens": {"type": "array", "items": {"type": "integer"}},
    },
}


def validate_completion(value, screen_count):
    if not isinstance(value, dict) or set(value) != set(COMPLETION_SCHEMA["required"]):
        raise PlannerResponseError("Invalid completion review fields")
    if value["decision"] not in {"complete", "continue", "needs_guidance"}:
        raise PlannerResponseError("Invalid completion decision")
    if not isinstance(value["reason"], str) or not value["reason"].strip():
        raise PlannerResponseError("Completion review requires a reason")
    gaps = value["gaps"]
    if not isinstance(gaps, list) or any(not isinstance(x, str) or not x.strip() for x in gaps):
        raise PlannerResponseError("Completion gaps must be nonempty strings")
    refs = value["evidence_screens"]
    if not isinstance(refs, list) or any(type(x) is not int or not 0 <= x < screen_count for x in refs):
        raise PlannerResponseError("Completion review cites unavailable screens")
    if value["decision"] == "complete" and (gaps or not refs):
        raise PlannerResponseError("Completion requires evidence and no unresolved objective gaps")
    if value["decision"] != "complete" and not gaps:
        raise PlannerResponseError("Incomplete review must explain missing evidence or guidance")
    return value
