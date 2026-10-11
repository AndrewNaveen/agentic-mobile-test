"""Independent deterministic verification for the first agentic slice."""

from __future__ import annotations

from typing import Protocol

from .contracts import (
    AssertionCheck,
    Observation,
    Scenario,
    VerificationResult,
    VerificationState,
)


class Verifier(Protocol):
    def evaluate(self, scenario: Scenario, observation: Observation) -> VerificationResult: ...


class VisibleTextVerifier:
    """Check approved visible-text assertions without asking the planner."""

    def evaluate(self, scenario: Scenario, observation: Observation) -> VerificationResult:
        visible_values = tuple(
            value
            for element in observation.elements
            for value in (element.text, element.accessibility_id, element.label)
            if value
        )
        checks = tuple(
            self._check(assertion.assertion_id, assertion.text, assertion.exact, visible_values)
            for assertion in scenario.assertions
        )
        passed = all(check.passed for check in checks)
        return VerificationResult(
            state=VerificationState.PASSED if passed else VerificationState.PENDING,
            checks=checks,
            summary=(
                "All approved assertions are satisfied"
                if passed
                else "One or more approved assertions are not yet observable"
            ),
        )

    @staticmethod
    def _check(
        assertion_id: str,
        expected: str,
        exact: bool,
        visible_values: tuple[str, ...],
    ) -> AssertionCheck:
        if exact:
            passed = expected in visible_values
        else:
            passed = any(expected in value for value in visible_values)
        return AssertionCheck(
            assertion_id=assertion_id,
            passed=passed,
            detail=(
                f"Observed expected text: {expected!r}"
                if passed
                else f"Expected text is not visible: {expected!r}"
            ),
        )
