"""Offline exploration tests; no model requests or device connections."""

import json
from pathlib import Path

import pytest

from agentic_mobile_test.agent.exploration import ExplorationBrief, ExplorationLoop, ExplorationPlanner
from agentic_mobile_test.agent.planner import ModelGatewayUnavailableError
from agentic_mobile_test.contracts import ExecutionResult, Observation, ObservedElement


def brief(**changes):
    return ExplorationBrief(**dict({
        "objective": "Explore demo media player navigation",
        "app_package": "test.app", "starting_state": "Overview",
        "boundaries": ("Do not change account settings",),
        "cleanup": "Return to Overview manually", "sandbox_confirmed": True,
        "max_steps": 3,
    }, **changes))


def response(action="tap", target="e1"):
    return dict(action=action, target_ref=target, value_ref=None,
                reason="Inspect the player", expected_effect="Player controls may appear")


class Gateway:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.payloads = []

    def choose_exploration(self, **request):
        self.payloads.append(request["payload"])
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        return answer


class Observer:
    def __init__(self, root, *, package="test.app", fail_after=False, toggle=False):
        self.root, self.package = root, package
        self.calls = 0
        self.fail_after, self.toggle = fail_after, toggle

    def observe(self):
        self.calls += 1
        if self.fail_after and self.calls > 1:
            raise RuntimeError("Capture failed")
        screenshot, source = self.root / "screen.png", self.root / "screen.xml"
        screenshot.write_bytes(b"fake screenshot")
        source.write_text("<hierarchy/>")
        return Observation(self.calls, f"screen-{self.calls}", screenshot, source, (
            ObservedElement("e1", "Player", text="Player", clickable=True,
                            toggles_state=self.toggle, locator_strategy="id", locator_value="player"),
        ), self.package)


class Executor:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def execute(self, *args):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Command outcome unknown")
        return ExecutionResult("tap", 0.01)


def run(tmp_path, answers, *, config=None, observer=None, executor=None):
    gateway = Gateway(answers)
    executor = executor or Executor()
    result = ExplorationLoop(planner=ExplorationPlanner(gateway),
                             observer=observer or Observer(tmp_path), executor=executor).run(
        config or brief(), runs_directory=tmp_path / "runs")
    return result, json.loads(result.report_path.read_text()), gateway, executor


def test_explores_without_assertions_and_records_backtracking(tmp_path):
    result, report, gateway, executor = run(tmp_path, [response(), response("press_back", None),
                                                     response("finish", None)])
    assert result.status == "completed"
    assert executor.calls == 2
    assert len(report["screens"]) == 3
    assert len(gateway.payloads[-1]["attempts"]) == 2
    assert report["generation_status"] == "not_a_regression_candidate"
    assert report["cleanup"]["status"] == "caller_owned_not_verified"
    assert not (result.report_path.parent / "discovered-path.json").exists()
    assert (result.report_path.parent / report["screens"][0]["evidence"]["screenshot"]["path"]).exists()


@pytest.mark.parametrize("action,status", [("request_guidance", "needs_guidance"), ("finish", "completed")])
def test_stop_never_reaches_executor(tmp_path, action, status):
    result, _, _, executor = run(tmp_path, [response(action, None)])
    assert result.status == status
    assert executor.calls == 0


@pytest.mark.parametrize("answer", [response(target="invented"), response("launch_app", None)])
def test_policy_rejects_unapproved_actions(tmp_path, answer):
    result, report, _, executor = run(tmp_path, [answer])
    assert result.status == "blocked"
    assert report["attempts"][0]["execution_status"] == "not_executed"
    assert executor.calls == 0


def test_toggle_changes_denied_by_default(tmp_path):
    result, _, _, executor = run(tmp_path, [response()], observer=Observer(tmp_path, toggle=True))
    assert result.status == "blocked"
    assert executor.calls == 0


def test_wrong_app_stops_before_model_call(tmp_path):
    result, report, gateway, executor = run(tmp_path, [], observer=Observer(tmp_path, package="other"))
    assert result.status == "blocked"
    assert not gateway.payloads
    assert executor.calls == 0
    assert len(report["screens"]) == 1


def test_budget_exhaustion_is_not_success(tmp_path):
    result, _, _, executor = run(tmp_path, [response()], config=brief(max_steps=1))
    assert result.status == "budget_exhausted"
    assert executor.calls == 1


@pytest.mark.parametrize("executor_fails", [False, True])
def test_incomplete_attempt_survives_errors(tmp_path, executor_fails):
    result, report, _, _ = run(tmp_path, [response()],
        observer=Observer(tmp_path, fail_after=True), executor=Executor(fail=executor_fails))
    assert result.status == "error"
    attempt = report["attempts"][0]
    assert attempt["execution_status"] == ("started_outcome_unknown" if executor_fails else "returned")
    assert "after_screen" not in attempt


def test_gateway_limit_preserves_partial_report(tmp_path):
    result, report, _, _ = run(tmp_path, [response(), ModelGatewayUnavailableError("budget")])
    assert result.status == "blocked"
    assert len(report["attempts"]) == 1


def test_invalid_stop_does_not_complete(tmp_path):
    result, _, _, executor = run(tmp_path, [response("finish", "e1")])
    assert result.status == "error"
    assert executor.calls == 0


def test_explicit_sandbox_acknowledgment_required():
    with pytest.raises(ValueError, match="isolated"):
        brief(sandbox_confirmed=False)
