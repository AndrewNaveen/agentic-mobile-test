"""One immutable candidate and evidence-linked model reviews, not test verdicts."""

from typing import Any, Mapping

from .protocol import PlannerResponseError


PROPOSAL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["scenario", "criterion", "basis", "source_ref"],
    "properties": {
        "scenario": {"type": "string"}, "criterion": {"type": "string"},
        "basis": {"type": "string", "enum": ["hypothesis", "supplied_reference"]},
        "source_ref": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
}
REVIEW_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["assessment", "evidence_steps", "explanation", "open_question"],
    "properties": {
        "assessment": {"type": "string", "enum": ["supported", "contradicted", "inconclusive"]},
        "evidence_steps": {"type": "array", "items": {"type": "integer"}},
        "explanation": {"type": "string"}, "open_question": {"type": "string"},
    },
}


def record_investigation(response: Mapping[str, Any], report: dict, references: Mapping[str, str]) -> str:
    """Validate provenance/trace links; semantic truth still requires human review."""
    required = {"action", "target_ref", "value_ref", "reason", "expected_effect"}
    optional = {"proposal", "review", "target_percent", "start_percent", "end_percent"}
    if not required <= set(response) or set(response) - required - optional:
        raise PlannerResponseError("Invalid investigation response fields")
    if any(not isinstance(response[key], str) or not response[key].strip()
           for key in ("reason", "expected_effect")):
        raise PlannerResponseError("Investigation requires reason and expected_effect")
    for field in ("target_ref", "value_ref", "target_percent", "start_percent", "end_percent"):
        if response.get(field) is not None:
            raise PlannerResponseError("Investigation notes cannot execute UI targets")
    action = response["action"]
    key, schema = ("proposal", PROPOSAL_SCHEMA) if action == "propose" else ("review", REVIEW_SCHEMA)
    value = response.get(key)
    other = "review" if key == "proposal" else "proposal"
    if response.get(other) is not None:
        raise PlannerResponseError("Proposal and review must be separate decisions")
    if not isinstance(value, dict) or set(value) != set(schema["required"]):
        raise PlannerResponseError(f"Invalid {key} fields")
    for name, rule in schema["properties"].items():
        if rule.get("type") == "string":
            if not isinstance(value[name], str) or not value[name].strip():
                raise PlannerResponseError(f"{name} requires non-empty text")
            if "enum" in rule and value[name] not in rule["enum"]:
                raise PlannerResponseError(f"Invalid {name}")
    if action == "propose":
        if report["candidate"] is not None:
            if all(report["candidate"][key] == value[key] for key in PROPOSAL_SCHEMA["required"]):
                return "already_recorded"
            raise PlannerResponseError("One candidate per experiment; do not rewrite its criterion")
        source = value["source_ref"]
        if value["basis"] == "supplied_reference":
            if not isinstance(source, str) or source not in references:
                raise PlannerResponseError("Unknown supplied reference")
        elif source is not None:
            raise PlannerResponseError("A hypothesis must not claim a source reference")
        report["candidate"] = dict(value, proposed_at_step=report["attempts"][-1]["step"],
                                   approval="not_approved")
        return "recorded"
    candidate = report["candidate"]
    if candidate is None:
        raise PlannerResponseError("Propose a criterion before reviewing it")
    ids = value["evidence_steps"]
    if not isinstance(ids, list) or any(type(x) is not int for x in ids) or len(set(ids)) != len(ids):
        raise PlannerResponseError("evidence_steps must contain unique integer step IDs")
    complete = {attempt["step"] for attempt in report["attempts"]
                if attempt["execution_status"] == "returned" and "after_screen" in attempt
                and attempt["step"] > candidate["proposed_at_step"]}
    if not set(ids) <= complete:
        raise PlannerResponseError("Review must cite completed actions after the proposal")
    if value["assessment"] != "inconclusive" and not ids:
        raise PlannerResponseError("Supported/contradicted claims require action evidence")
    report["reviews"].append(dict(value, reviewed_at_step=report["attempts"][-1]["step"],
                                  authority="model_assessment_requires_human_review"))
    return "recorded"
