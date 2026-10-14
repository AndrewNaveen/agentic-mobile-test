"""Bounded observe-plan-policy-act-verify orchestration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Protocol

from ..contracts import (
    ExecutionResult,
    Observation,
    PlannedAction,
    RunOutcome,
    RunResult,
    Scenario,
    StepRecord,
    TextExpectation,
    VerificationResult,
    VerificationState,
)
from ..evidence.artifacts import RunArtifacts
from ..verification.verifier import Verifier
from .planner import ModelGatewayUnavailableError, Planner, PlannerContext
from .policy import ActionPolicy


class Observer(Protocol):
    def observe(self) -> Observation: ...

    def wait_for_clickable_text(
        self,
        text: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> Observation: ...


class Executor(Protocol):
    def execute(
        self,
        scenario: Scenario,
        action: PlannedAction,
        observation: Observation,
    ) -> ExecutionResult: ...


class RunBlockedError(RuntimeError):
    """A required external precondition or resource is unavailable."""


class AgentLoop:
    def __init__(
        self,
        *,
        planner: Planner,
        observer: Observer,
        policy: ActionPolicy,
        executor: Executor,
        verifier: Verifier,
    ) -> None:
        self.planner = planner
        self.observer = observer
        self.policy = policy
        self.executor = executor
        self.verifier = verifier

    def run(self, scenario: Scenario, *, runs_directory: Path | None = None) -> RunResult:
        artifacts = RunArtifacts.create(runs_directory, scenario) if runs_directory else None
        history: list[StepRecord] = []
        verification: VerificationResult | None = None

        try:
            observation = self.observer.observe()
            verification = self.verifier.evaluate(scenario, observation)
            terminal = _terminal_result(scenario, history, verification)
            if terminal is not None:
                return _finish(terminal, artifacts)

            for step_number in range(1, scenario.max_steps + 1):
                observation = _wait_for_visible_required_targets(
                    self.observer,
                    scenario,
                    history,
                    observation,
                    verification,
                )
                action = self.planner.decide(
                    PlannerContext(
                        scenario=scenario,
                        observation=observation,
                        history=tuple(history),
                        remaining_steps=scenario.max_steps - step_number + 1,
                    )
                )
                self.policy.validate(
                    scenario=scenario,
                    action=action,
                    observation=observation,
                    history=tuple(history),
                    step_number=step_number,
                )
                execution = self.executor.execute(scenario, action, observation)
                after = self.observer.observe()
                step = StepRecord(
                    step_number=step_number,
                    before=observation,
                    action=action,
                    execution=execution,
                    after=after,
                )
                history.append(step)
                if artifacts:
                    artifacts.record_step(step)

                observation = after
                verification = self.verifier.evaluate(scenario, observation)
                terminal = _terminal_result(scenario, history, verification)
                if terminal is not None:
                    return _finish(terminal, artifacts)

            return _finish(
                RunResult(
                    scenario_id=scenario.scenario_id,
                    outcome=RunOutcome.TEST_FAILURE,
                    summary="Step budget exhausted before the assertions were satisfied",
                    steps=tuple(history),
                    final_verification=verification,
                ),
                artifacts,
            )
        except (RunBlockedError, ModelGatewayUnavailableError) as error:
            result = RunResult(
                scenario_id=scenario.scenario_id,
                outcome=RunOutcome.BLOCKED,
                summary=str(error),
                steps=tuple(history),
                final_verification=verification,
            )
            return _finish(result, artifacts)
        except Exception as error:
            result = RunResult(
                scenario_id=scenario.scenario_id,
                outcome=RunOutcome.TEST_FAILURE,
                summary=f"{type(error).__name__}: {error}",
                steps=tuple(history),
                final_verification=verification,
            )
            return _finish(result, artifacts)


def _terminal_result(
    scenario: Scenario,
    history: list[StepRecord],
    verification: VerificationResult,
) -> RunResult | None:
    if verification.state is VerificationState.PASSED:
        if not _required_interactions_satisfied(scenario, history):
            return None
        if not history and any(
            assertion.expectation is TextExpectation.ABSENT
            for assertion in scenario.assertions
        ):
            return None
        return RunResult(
            scenario_id=scenario.scenario_id,
            outcome=RunOutcome.PASSED,
            summary=verification.summary,
            steps=tuple(history),
            final_verification=verification,
        )
    if verification.state is VerificationState.PRODUCT_FAILURE:
        return RunResult(
            scenario_id=scenario.scenario_id,
            outcome=RunOutcome.PRODUCT_FAILURE,
            summary=verification.summary,
            steps=tuple(history),
            final_verification=verification,
        )
    return None


def _required_interactions_satisfied(
    scenario: Scenario,
    history: list[StepRecord],
) -> bool:
    for requirement in scenario.required_interactions:
        expected = " ".join(requirement.target_text.casefold().split())
        count = 0
        for step in history:
            if step.action.kind is not requirement.action or not step.action.target_ref:
                continue
            target = step.before.element(step.action.target_ref)
            observed = target.text or target.label if target is not None else ""
            if " ".join(observed.casefold().split()) == expected:
                count += 1
        if count < requirement.minimum_count:
            return False
    return True


def _wait_for_visible_required_targets(
    observer: Observer,
    scenario: Scenario,
    history: list[StepRecord],
    observation: Observation,
    verification: VerificationResult,
) -> Observation:
    current = observation
    for requirement in scenario.required_interactions:
        if requirement.action.value != "tap":
            continue
        expected = " ".join(requirement.target_text.casefold().split())
        completed = sum(
            1
            for step in history
            if step.action.kind is requirement.action
            and step.action.target_ref is not None
            and (target := step.before.element(step.action.target_ref)) is not None
            and " ".join((target.text or target.label).casefold().split()) == expected
        )
        if completed >= requirement.minimum_count:
            continue

        matches = [
            element
            for element in current.elements
            if " ".join((element.text or element.label).casefold().split()) == expected
        ]
        target_assertions = {
            assertion.assertion_id
            for assertion in scenario.assertions
            if " ".join(assertion.text.casefold().split()) == expected
        }
        other_assertions_passed = bool(target_assertions) and all(
            check.passed
            for check in verification.checks
            if check.assertion_id not in target_assertions
        )
        target_not_ready = matches and not any(
            element.enabled and element.clickable for element in matches
        )
        target_still_loading = not matches and other_assertions_passed
        if target_not_ready or target_still_loading:
            current = observer.wait_for_clickable_text(
                requirement.target_text,
                timeout_seconds=10.0,
            )
    return current


def _finish(result: RunResult, artifacts: RunArtifacts | None) -> RunResult:
    if artifacts is None:
        return result
    completed = replace(result, run_directory=artifacts.run_directory)
    artifacts.finish(completed)
    return completed
