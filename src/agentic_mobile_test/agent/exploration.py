"""Bounded reconnaissance, separate from assertion-driven test discovery.

Reports are observations for human review, never successful regression paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from importlib.resources import files
import json
import re
from pathlib import Path
import shutil
from typing import Any, Mapping, Protocol
from uuid import uuid4

from ..contracts import ActionKind, Observation, StepRecord
from ..appium.models import AppiumActionError, SliderValueUnavailableError
from ..evidence.serialization import _jsonable
from .protocol import ModelBudgetExhaustedError, ModelGatewayUnavailableError, PlannerResponseError, _parse_action
from .policy import ActionPolicy, PolicyViolation
from .investigation import record_investigation
from .completion import validate_completion


@dataclass(frozen=True)
class ExplorationBrief:
    objective: str
    app_package: str
    boundaries: tuple[str, ...]
    app_slug: str
    investigation_slug: str
    starting_state: str = "Observe the current screen"
    cleanup: str = "Manually restore changed demo state and return to the landing page"
    references: Mapping[str, str] = field(default_factory=dict)
    sandbox_confirmed: bool = False
    max_steps: int = 10
    allow_toggle_changes: bool = False
    allowed_actions: frozenset[ActionKind] = frozenset({
        ActionKind.TAP, ActionKind.SCROLL_FORWARD,
        ActionKind.SCROLL_BACKWARD, ActionKind.PRESS_BACK,
    })
    # No text entry or launching arbitrary apps in this first exploration mode.
    test_data: Mapping[str, str] = field(default_factory=dict, init=False, repr=False)
    launchable_apps: Mapping[str, str] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        for name in ("app_slug", "investigation_slug"):
            value = getattr(self, name)
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) or len(value) > 80:
                raise ValueError(f"{name} must be a lowercase hyphenated name, at most 80 characters")
        if not isinstance(self.references, Mapping) or any(
            not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
            for k, v in self.references.items()
        ):
            raise ValueError("references must map source IDs to supplied excerpts or requirements")
        if not all(isinstance(value, str) and value.strip() for value in (
            self.objective, self.app_package, self.starting_state, self.cleanup,
        )):
            raise ValueError("Exploration requires objective, app, starting state and cleanup")
        if self.sandbox_confirmed is not True:
            raise ValueError("Explicitly confirm an isolated test environment before exploration")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 50:
            raise ValueError("max_steps must be an integer between 1 and 50")
        if type(self.allow_toggle_changes) is not bool:
            raise ValueError("allow_toggle_changes must be a boolean")
        if not self.boundaries or any(not isinstance(x, str) or not x.strip() for x in self.boundaries):
            raise ValueError("Provide non-empty exploration boundaries")
        permitted = {ActionKind.TAP, ActionKind.SCROLL_FORWARD,
                     ActionKind.SCROLL_BACKWARD, ActionKind.PRESS_BACK,
                     ActionKind.SET_SLIDER_VALUE, ActionKind.DRAG_SLIDER}
        if not self.allowed_actions or not self.allowed_actions <= permitted:
            raise ValueError("Exploration supports tap, scroll, back, set_slider_value and drag_slider")

    @classmethod
    def load(cls, path: Path) -> ExplorationBrief:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Exploration brief must be an object")
        if not isinstance(value.get("boundaries"), list):
            raise ValueError("boundaries must be a list of strings")
        value["boundaries"] = tuple(value.get("boundaries", ()))
        if "allowed_actions" in value:
            if not isinstance(value["allowed_actions"], list):
                raise ValueError("allowed_actions must be a list")
            value["allowed_actions"] = frozenset(ActionKind(x) for x in value["allowed_actions"])
        return cls(**value)


class ExplorationGateway(Protocol):
    def choose_exploration(
        self, *, system_instruction: str, payload: Mapping[str, Any], screenshot: Path,
    ) -> Mapping[str, Any]: ...

    def review_completion(self, *, system_instruction: str, payload: Mapping[str, Any],
                          screenshots: tuple[Path, ...]) -> Mapping[str, Any]: ...


class ExplorationPlanner:
    def __init__(self, gateway: ExplorationGateway):
        self.gateway = gateway
        self.instruction = files("agentic_mobile_test.prompts").joinpath("exploration.md").read_text(encoding="utf-8")
        self.review_instruction = files("agentic_mobile_test.prompts").joinpath("completion.md").read_text(encoding="utf-8")
        if not self.instruction.strip() or not self.review_instruction.strip():
            raise ValueError("Exploration instruction must not be empty")

    def decide(self, brief: ExplorationBrief, observation: Observation,
               screens: list[dict], attempts: list[dict], remaining: int,
               candidate: dict | None = None, reviews: list[dict] | None = None,
               completion_reviews: list[dict] | None = None) -> Mapping[str, Any]:
        return self.gateway.choose_exploration(
            system_instruction=self.instruction,
            screenshot=observation.screenshot,
            payload={
                "mode": "exploration", "brief": _jsonable(brief),
                "remaining_steps": remaining,
                "current_screen": _screen(observation),
                "visited_screens": _jsonable(screens),
                "attempts": _jsonable(attempts),
                "candidate": _jsonable(candidate), "reviews": _jsonable(reviews or []),
                "completion_reviews": _jsonable(completion_reviews or []),
                "action_schema": {
                    "action": sorted(x.value for x in brief.allowed_actions) + ["propose", "review", "finish", "request_guidance"],
                    "target_ref": "current element ref for tap or slider actions; otherwise null",
                    "value_ref": "null",
                    "target_percent": "absolute percentage 0..100 for set_slider_value; otherwise null",
                    "start_percent": "track position 0..100 for drag_slider; otherwise null",
                    "end_percent": "track position 0..100 for drag_slider, 1..30 points from start; otherwise null",
                    "reason": "short reasoning, or uncertainty needing human review",
                    "expected_effect": "predicted effect, not a verified finding",
                    "scroll_forward": "reveal later/lower content",
                    "scroll_backward": "reveal earlier/upper content",
                },
            },
        )


@dataclass(frozen=True)
class ExplorationResult:
    status: str
    summary: str
    report_path: Path


def create_run_directory(brief: ExplorationBrief, runs_directory: Path) -> Path:
    """Allocate one mobile investigation directory before capture begins."""
    run_id = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S.%fZ") + "-" + uuid4().hex[:8]
    directory = runs_directory / "apps" / brief.app_slug / brief.investigation_slug / run_id
    directory.mkdir(parents=True, exist_ok=False)
    return directory


class ExplorationLoop:
    def __init__(self, *, planner: ExplorationPlanner, observer: Any,
                 executor: Any, reviewer: ExplorationGateway, policy: ActionPolicy | None = None):
        self.planner, self.observer, self.executor = planner, observer, executor
        if reviewer is planner.gateway:
            raise ValueError("Final review requires an independently budgeted gateway")
        self.reviewer = reviewer
        self.policy = policy or ActionPolicy()

    def run(self, brief: ExplorationBrief, *, runs_directory: Path,
            run_directory: Path | None = None) -> ExplorationResult:
        directory = run_directory if run_directory is not None else create_run_directory(brief, runs_directory)
        expected_parent = runs_directory / "apps" / brief.app_slug / brief.investigation_slug
        if directory.resolve().parent != expected_parent.resolve():
            raise ValueError("Run directory must belong to the brief's app and investigation")
        if not directory.is_dir() or any(p.name != "diagnostics" for p in directory.iterdir()):
            raise ValueError("Run directory must be newly allocated; existing evidence cannot be overwritten")
        report_path = directory / "exploration.json"
        prompt_bytes = self.planner.instruction.encode("utf-8")
        (directory / "system-prompt.md").write_bytes(prompt_bytes)
        review_bytes = self.planner.review_instruction.encode("utf-8")
        (directory / "completion-prompt.md").write_bytes(review_bytes)
        screens: list[dict] = []
        attempts: list[dict] = []
        history: list[StepRecord] = []
        consecutive_rejections = 0
        consecutive_note_rejections = 0
        report = {
            "schema_version": 2, "record_type": "exploration_report",
            "prompt": {"resource": "agentic_mobile_test.prompts/exploration.md",
                       "path": "system-prompt.md", "sha256": sha256(prompt_bytes).hexdigest()},
            "candidate": None, "reviews": [],
            "completion_reviews": [], "model_decisions": 0,
            "budgets": {"exploration": _jsonable(getattr(self.planner.gateway, "budget", None)),
                        "final_review": _jsonable(getattr(self.reviewer, "budget", None))},
            "completion_prompt": {"path": "completion-prompt.md",
                                  "sha256": sha256(review_bytes).hexdigest()},
            "generation_status": "not_a_regression_candidate",
            "brief": _jsonable(brief), "screens": screens, "attempts": attempts,
            "cleanup": {"status": "caller_owned_not_verified", "instructions": brief.cleanup},
            "status": "running", "summary": "Exploration in progress",
        }

        def save() -> None:
            usage = getattr(self.planner.gateway, "usage", None)
            if usage is not None:
                report["model_usage"] = _jsonable(usage)
            review_usage = getattr(self.reviewer, "usage", None)
            if review_usage is not None:
                report["review_usage"] = _jsonable(review_usage)
            if usage is not None and review_usage is not None:
                report["total_estimated_cost_usd"] = str(usage.estimated_cost_usd + review_usage.estimated_cost_usd)
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            (directory / "brief.json").write_text(json.dumps(report["brief"], indent=2) + "\n", encoding="utf-8")
            (directory / "actions.jsonl").write_text(
                "".join(json.dumps(attempt) + "\n" for attempt in attempts), encoding="utf-8")
            (directory / "report.md").write_text(_report_markdown(report), encoding="utf-8")

        def observe() -> Observation:
            observed = self.observer.observe()
            record = _screen(observed)
            record["evidence"] = {}
            screen_directory = directory / "screens" / f"{len(screens):03d}"
            screen_directory.mkdir(parents=True)
            for kind, source in (("screenshot", observed.screenshot), ("ui_source", observed.ui_source)):
                destination = screen_directory / ("screenshot.png" if kind == "screenshot" else "hierarchy.xml")
                shutil.copyfile(source, destination)
                record["evidence"][kind] = {
                    "path": str(destination.relative_to(directory)),
                    "sha256": sha256(destination.read_bytes()).hexdigest(),
                }
            screens.append(record)
            save()
            if observed.app_package != brief.app_package:
                raise PolicyViolation("Observed app is outside the approved package; stopping")
            return observed

        save()
        try:
            current = observe()
            number = 0
            while number < brief.max_steps:
                number += 1
                report["model_decisions"] = number
                save()
                response = self.planner.decide(brief, current, screens, attempts,
                                               brief.max_steps - number + 1,
                                               report["candidate"], report["reviews"],
                                               report["completion_reviews"])
                # Retain every proposed command, including rejected ones.
                attempt = {"step": number, "before_screen": len(screens) - 1,
                           "proposal": dict(response), "execution_status": "not_executed"}
                attempts.append(attempt)
                save()
                if response.get("action") in {"propose", "review"}:
                    try:
                        outcome = record_investigation(response, report, brief.references)
                        attempt["note_status"] = outcome
                        attempt["investigation_feedback"] = (
                            "Already recorded; original criterion unchanged. Choose an action, review, or request guidance."
                            if outcome == "already_recorded" else
                            "Recorded successfully. Continue investigating or review the evidence; do not repeat this note."
                        )
                        consecutive_note_rejections = consecutive_note_rejections + 1 if outcome == "already_recorded" else 0
                    except PlannerResponseError as error:
                        attempt.update(note_status="rejected", investigation_feedback=str(error))
                        consecutive_note_rejections += 1
                    save()
                    if consecutive_note_rejections >= 3:
                        report.update(status="blocked", summary="Stopped after 3 duplicate or invalid investigation notes")
                        break
                    continue
                if response.get("proposal") is not None or response.get("review") is not None:
                    attempt.update(
                        execution_status="rejected",
                        note_status="rejected",
                        investigation_feedback=(
                            "Nothing executed or recorded. UI actions, finish and request_guidance "
                            "require proposal=null and review=null. Send a separate propose or "
                            "review decision to record a finding, or resubmit just the UI action."
                        ),
                    )
                    consecutive_note_rejections += 1
                    save()
                    if consecutive_note_rejections >= 3:
                        report.update(status="blocked", summary="Stopped after 3 invalid investigation decisions")
                        break
                    continue
                response = {k: v for k, v in response.items() if k not in {"proposal", "review"}}
                if response.get("action") in {"finish", "request_guidance"}:
                    fields = {"action", "target_ref", "value_ref", "reason", "expected_effect"}
                    if (set(response) - {"target_percent", "start_percent", "end_percent"} != fields
                            or any(response.get(key) is not None for key in
                                   ("target_percent", "start_percent", "end_percent"))
                            or response["target_ref"] is not None
                            or response["value_ref"] is not None
                            or any(not isinstance(response[x], str) or not response[x].strip()
                                   for x in ("reason", "expected_effect"))):
                        raise PlannerResponseError("Invalid exploration stop response")
                    if response["action"] == "request_guidance":
                        report.update(status="needs_guidance", summary=response["reason"])
                        break
                    report.update(status="review_pending", summary=response["reason"])
                    break
                action = _parse_action(response)
                try:
                    self.policy.validate(scenario=brief, action=action, observation=current,
                                         history=tuple(history), step_number=number)
                except PolicyViolation as error:
                    consecutive_rejections += 1
                    attempt.update(
                        execution_status="rejected",
                        policy_feedback=str(error),
                    )
                    save()
                    if consecutive_rejections >= 3:
                        report.update(status="blocked", summary=(
                            f"Stopped after 3 rejected actions without execution: {error}"))
                        break
                    # A new decision consumes the existing step/model budget.
                    # Refresh the screen rather than proposing against stale refs.
                    if number < brief.max_steps:
                        current = observe()
                    continue
                consecutive_rejections = 0
                consecutive_note_rejections = 0
                attempt["execution_status"] = "started_outcome_unknown"
                save()
                try:
                    execution = self.executor.execute(brief, action, current)
                except AppiumActionError as error:
                    attempt.update(execution_status="failed_outcome_unknown", error=str(error))
                    if error.evidence is not None:
                        attempt["failure_evidence"] = _jsonable(error.evidence)
                    save()
                    if (action.kind is ActionKind.SET_SLIDER_VALUE
                            and isinstance(error.__cause__, SliderValueUnavailableError)):
                        report.update(
                            status="needs_guidance",
                            summary=f"Slider value cannot be observed or verified: {error}. "
                            "Provide a reviewed value reader before continuing slider exploration.",
                        )
                        break
                    raise
                attempt.update(execution_status="returned", execution=_jsonable(execution))
                save()  # Preserve the action even if the next observation fails.
                after = observe()
                attempt.update(after_screen=len(screens) - 1,
                               screen_changed=current.fingerprint != after.fingerprint)
                history.append(StepRecord(number, current, action, execution, after))
                current = after
                save()
            else:
                report.update(status="budget_exhausted", summary="Exploration decision limit reached; final review will assess the evidence")
        except ModelBudgetExhaustedError as error:
            report.update(status="budget_exhausted", summary=str(error))
        except (PolicyViolation, ModelGatewayUnavailableError) as error:
            report.update(status="blocked", summary=f"{type(error).__name__}: {error}")
        except Exception as error:
            report.update(status="error", summary=f"{type(error).__name__}: {error}")
        finally:
            save()

        # Terminal review is independent of every exploration stop condition. No
        # model decision can restart device actions from this phase.
        report["exploration_outcome"] = {"status": report["status"], "summary": report["summary"]}
        review_record = {"step": "final", "status": "started",
                         "authority": "model_assessment_not_product_verdict"}
        report["completion_reviews"].append(review_record)
        save()
        try:
            if not screens:
                raise ModelGatewayUnavailableError("No captured screen evidence is available for final review")
            reviewed = self.reviewer.review_completion(
                system_instruction=self.planner.review_instruction,
                payload={"brief": report["brief"], "screens": screens,
                         "attempts": attempts, "candidate": report["candidate"],
                         "reviews": report["reviews"],
                         "exploration_outcome": report["exploration_outcome"],
                         "automatic_continuation": False},
                screenshots=tuple(directory / s["evidence"]["screenshot"]["path"] for s in screens),
            )
            review_record["response"] = dict(reviewed)
            save()
            validated = validate_completion(dict(reviewed), len(screens))
            review_record["status"] = "returned"
            if report["status"] == "review_pending":
                report.update(status="completed" if validated["decision"] == "complete" else "needs_guidance",
                              summary=validated["reason"])
            # Preserve budget, policy, provider and execution stops even if the
            # reviewer considers the observed behavior sufficient.
        except Exception as error:
            review_record.update(status="review_unavailable", error=f"{type(error).__name__}: {error}")
            if report["status"] != "error":
                report.update(status="review_unavailable", summary=review_record["error"])
        finally:
            save()
        return ExplorationResult(report["status"], report["summary"], report_path)


def _screen(observation: Observation) -> dict:
    if observation.compact_xml:
        return {
            "fingerprint": observation.fingerprint,
            "app_package": observation.app_package, "activity": observation.activity,
            "ui_xml": observation.compact_xml,
        }
    return {
        "fingerprint": observation.fingerprint,
        "app_package": observation.app_package, "activity": observation.activity,
        "elements": [
            {"ref": e.ref, "text": e.text, "accessibility_id": e.accessibility_id,
             "clickable": e.clickable, "enabled": e.enabled, "checked": e.checked,
             "toggles_state": e.toggles_state, "executable": e.executable,
             "is_slider": e.is_slider, "slider_value_hint": e.slider_value_hint}
            for e in observation.elements
        ],
    }


def _report_markdown(report: dict) -> str:
    lines = ["# UI investigation", "", f"Status: {report['status']}", "",
             report["summary"], "", "No product verdict. Candidate criteria and model reviews require human approval.", "",
             "## Candidate behavior", ""]
    candidate = report["candidate"]
    if candidate:
        lines += [f"Scenario: {candidate['scenario']}", "",
                  f"Proposed criterion: {candidate['criterion']}", "",
                  f"Basis: {candidate['basis']}; source: {candidate['source_ref'] or 'none (hypothesis)'}. Approval: not approved.", ""]
    else:
        lines += ["No candidate proposed yet.", ""]
    lines += ["## Evidence reviews (model assessments)", ""]
    for review in report["reviews"]:
        lines += [f"- {review['assessment']}: {review['explanation']}",
                  f"  Evidence action steps: {review['evidence_steps']}",
                  f"  Open question: {review['open_question']}"]
    lines += ["", "## Final completion review", ""]
    if "exploration_outcome" in report:
        lines.append("Exploration stop: " + json.dumps(report["exploration_outcome"]))
    for review in report.get("completion_reviews", []):
        lines.append(f"- Completion review {review['step']}: {review['status']}")
        if "response" in review:
            lines.append("  " + json.dumps(review["response"]))
        if "error" in review:
            lines.append("  " + review["error"])
    lines += ["", "## Action trail", ""]
    for attempt in report["attempts"]:
        lines.append(f"- Step {attempt['step']}: {attempt['proposal'].get('action')}; "
                     f"execution: {attempt['execution_status']}; "
                     f"screen {attempt['before_screen']} → {attempt.get('after_screen', 'not captured / note only')}")
        if "policy_feedback" in attempt:
            lines.append(f"  Not executed: {attempt['policy_feedback']}")
        if "investigation_feedback" in attempt:
            lines.append(f"  Note {attempt['note_status']}: {attempt['investigation_feedback']}")
    lines += ["", "## Screens", ""]
    for index, screen in enumerate(report["screens"]):
        evidence = screen["evidence"]
        lines.append(f"- Screen {index}: [screenshot]({evidence['screenshot']['path']}) / "
                     f"[UI XML]({evidence['ui_source']['path']})")
    lines += ["", "## Cleanup", "", "Not verified. " + report["cleanup"]["instructions"], ""]
    return "\n".join(lines)
