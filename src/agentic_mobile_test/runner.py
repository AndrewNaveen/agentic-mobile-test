"""Bounded observe-plan-policy-act-verify orchestration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Protocol

from .artifacts import RunArtifacts
from .contracts import (
    ExecutionResult,
    Observation,
    PlannedAction,
    RunOutcome,
    RunResult,
    Scenario,
    StepRecord,
    VerificationResult,
    VerificationState,
)
from .planner import ModelGatewayUnavailableError, Planner, PlannerContext
from .policy import ActionPolicy
from .verifier import Verifier


class Observer(Protocol):
    def observe(self) -> Observation: ...


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


def _finish(result: RunResult, artifacts: RunArtifacts | None) -> RunResult:
    if artifacts is None:
        return result
    completed = replace(result, run_directory=artifacts.run_directory)
    artifacts.finish(completed)
    return completed
