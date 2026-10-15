"""Independent deterministic verification for the first agentic slice."""

from __future__ import annotations

from typing import Protocol

from ..contracts import (
    AssertionCheck,
    Observation,
    ObservedElement,
    Scenario,
    TextAssertion,
    TextExpectation,
    VerificationResult,
    VerificationState,
)


class Verifier(Protocol):
    def evaluate(self, scenario: Scenario, observation: Observation) -> VerificationResult: ...


class TextVerifier:
    """Check text and optional Android checked state without asking the planner."""

    def evaluate(self, scenario: Scenario, observation: Observation) -> VerificationResult:
        visible_values = tuple(
            value
            for element in observation.elements
            for value in (element.text, element.accessibility_id, element.label)
            if value
        )
        checks = tuple(
            self._check_toggle(assertion, observation, visible_values)
            if assertion.checked is not None else self._check(
                assertion.assertion_id,
                assertion.text,
                assertion.exact,
                assertion.expectation,
                visible_values,
            )
            for assertion in scenario.assertions
        )
        passed = all(check.passed for check in checks)
        wrong_toggle = not scenario.allow_toggle_changes and any(
            assertion.checked is not None
            and self._check(assertion.assertion_id, assertion.text, assertion.exact,
                            assertion.expectation, visible_values).passed
            and len(candidates := self._toggle_candidates(assertion, observation)) == 1
            and candidates[0].checked is not None
            and candidates[0].checked is not assertion.checked
            for assertion in scenario.assertions
        )
        return VerificationResult(
            state=(VerificationState.PASSED if passed else
                   VerificationState.PRODUCT_FAILURE if wrong_toggle else VerificationState.PENDING),
            checks=checks,
            summary=("All approved assertions are satisfied" if passed
                     else "The observed toggle is in the wrong state; changes are forbidden" if wrong_toggle
                     else "One or more approved assertions are not yet observable"),
        )

    def _check_toggle(
        self, assertion: TextAssertion, observation: Observation,
        visible_values: tuple[str, ...],
    ) -> AssertionCheck:
        context = self._check(assertion.assertion_id, assertion.text, assertion.exact,
                              assertion.expectation, visible_values)
        candidates = self._toggle_candidates(assertion, observation)
        passed = context.passed and len(candidates) == 1 and candidates[0].checked is assertion.checked
        actual = candidates[0].checked if len(candidates) == 1 else "missing or ambiguous"
        return AssertionCheck(
            assertion.assertion_id, passed,
            f"{context.detail}; expected checked={assertion.checked}, observed={actual}",
        )

    @staticmethod
    def _toggle_candidates(assertion: TextAssertion, observation: Observation) -> list[ObservedElement]:
        return [
            element for element in observation.elements
            if (element.checked is not None or element.checkable) and (
                element.resource_id == assertion.resource_id
                if assertion.resource_id is not None else
                any(assertion.text == value if assertion.exact else assertion.text in value
                    for value in (element.text, element.accessibility_id, element.label, *element.toggle_labels) if value)
            )
        ]

    @staticmethod
    def _check(
        assertion_id: str,
        expected: str,
        exact: bool,
        expectation: TextExpectation,
        visible_values: tuple[str, ...],
    ) -> AssertionCheck:
        if exact:
            found = expected in visible_values
        else:
            found = any(expected in value for value in visible_values)
        passed = found if expectation is TextExpectation.VISIBLE else not found
        if expectation is TextExpectation.VISIBLE:
            detail = (
                f"Observed expected text: {expected!r}"
                if passed
                else f"Expected text is not visible: {expected!r}"
            )
        else:
            detail = (
                f"Confirmed text is absent: {expected!r}"
                if passed
                else f"Unexpected text is visible: {expected!r}"
            )
        return AssertionCheck(
            assertion_id=assertion_id,
            passed=passed,
            detail=detail,
        )
