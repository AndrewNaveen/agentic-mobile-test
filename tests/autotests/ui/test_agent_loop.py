"""Deterministic checks for the bounded agentic test architecture."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from agentic_mobile_test.appium.models import CapturedState
from agentic_mobile_test.appium.observer import AppiumObserver
from agentic_mobile_test.appium.executor import _scroll_path
from agentic_mobile_test.contracts import (
    ActionKind,
    ExecutionResult,
    Observation,
    ObservedElement,
    PlannedAction,
    RunOutcome,
    Scenario,
    StepRecord,
    VisibleTextAssertion,
)
from agentic_mobile_test.planner import (
    PlannerContext,
    PlannerResponseError,
    StructuredPlanner,
)
from agentic_mobile_test.policy import ActionPolicy, PolicyViolation
from agentic_mobile_test.runner import AgentLoop
from agentic_mobile_test.verifier import VisibleTextVerifier


def test_agent_loop_passes_only_after_independent_assertion(tmp_path: Path) -> None:
    initial = _observation(
        tmp_path,
        sequence=1,
        fingerprint="settings",
        elements=(
            ObservedElement(
                ref="e001",
                label="About phone",
                text="About phone",
                clickable=True,
                locator_strategy="accessibility id",
                locator_value="About phone",
            ),
        ),
    )
    completed = _observation(
        tmp_path,
        sequence=2,
        fingerprint="about-phone",
        elements=(
            ObservedElement(
                ref="e001",
                label="About phone",
                text="About phone",
            ),
            ObservedElement(
                ref="e002",
                label="Device name",
                text="Device name",
            ),
        ),
    )
    action = PlannedAction(
        kind=ActionKind.TAP,
        target_ref="e001",
        reason="The requested destination is visible",
        expected_effect="The About phone screen opens",
    )
    executor = _RecordingExecutor()
    loop = AgentLoop(
        planner=_QueuePlanner([action]),
        observer=_SequenceObserver([initial, completed]),
        policy=ActionPolicy(),
        executor=executor,
        verifier=VisibleTextVerifier(),
    )

    result = loop.run(_scenario(), runs_directory=tmp_path / "runs")

    assert result.outcome is RunOutcome.PASSED
    assert len(result.steps) == 1
    assert executor.actions == [action]
    assert result.run_directory is not None
    assert (result.run_directory / "scenario.json").is_file()
    assert (result.run_directory / "steps.jsonl").is_file()
    assert (result.run_directory / "result.json").is_file()
    scenario_artifact = (result.run_directory / "scenario.json").read_text(encoding="utf-8")
    assert "account_password" in scenario_artifact
    assert "do-not-write" not in scenario_artifact


def test_structured_planner_rejects_coordinate_invention(tmp_path: Path) -> None:
    planner = StructuredPlanner(
        _Gateway(
            {
                "action": "tap",
                "target_ref": "e001",
                "x": 400,
                "y": 800,
                "reason": "Tap the visible row",
                "expected_effect": "The next screen opens",
            }
        )
    )
    context = PlannerContext(
        scenario=_scenario(),
        observation=_observation(tmp_path, sequence=1, fingerprint="a"),
        history=(),
        remaining_steps=3,
    )

    with pytest.raises(PlannerResponseError, match="Unexpected planner fields"):
        planner.decide(context)


def test_policy_stops_repeated_ineffective_action(tmp_path: Path) -> None:
    observation = _observation(
        tmp_path,
        sequence=1,
        fingerprint="unchanged",
        elements=(
            ObservedElement(
                ref="e001",
                label="About phone",
                clickable=True,
                locator_strategy="accessibility id",
                locator_value="About phone",
            ),
        ),
    )
    action = PlannedAction(
        kind=ActionKind.TAP,
        target_ref="e001",
        reason="Open the screen",
        expected_effect="The screen changes",
    )
    execution = ExecutionResult("tap", 0.1)
    history = tuple(
        StepRecord(index, observation, action, execution, observation)
        for index in (1, 2)
    )

    with pytest.raises(PolicyViolation, match="ineffective action"):
        ActionPolicy(max_same_ineffective_actions=2).validate(
            scenario=_scenario(),
            action=action,
            observation=observation,
            history=history,
            step_number=3,
        )


def test_appium_observer_exposes_refs_and_keeps_locators_internal(tmp_path: Path) -> None:
    screenshot = tmp_path / "screen.png"
    screenshot.write_bytes(b"not-a-real-image")
    ui_source = tmp_path / "screen.xml"
    ui_source.write_text(
        """<hierarchy>
        <node class="android.widget.Button" text="Continue" content-desc="continue"
              clickable="true" enabled="true" />
        <node class="android.widget.TextView" text="Welcome" clickable="false"
              enabled="true" />
        </hierarchy>""",
        encoding="utf-8",
    )
    observer = AppiumObserver(
        _CaptureActions(CapturedState(screenshot=screenshot, ui_source=ui_source))
    )

    observation = observer.observe()

    assert observation.elements[0].ref == "e001"
    assert observation.elements[0].accessibility_id == "continue"
    assert observation.elements[0].locator_strategy == "accessibility id"
    assert observation.elements[1].locator_strategy == "-android uiautomator"
    assert observation.app_package == "com.example"


def test_appium_observer_inherits_clickability_from_android_row(tmp_path: Path) -> None:
    screenshot = tmp_path / "screen.png"
    screenshot.write_bytes(b"not-a-real-image")
    ui_source = tmp_path / "screen.xml"
    ui_source.write_text(
        """<hierarchy>
        <node class="android.widget.LinearLayout" clickable="true" enabled="true">
          <node class="android.widget.TextView" text="About emulated device"
                clickable="false" enabled="true" />
        </node>
        </hierarchy>""",
        encoding="utf-8",
    )
    observer = AppiumObserver(
        _CaptureActions(CapturedState(screenshot=screenshot, ui_source=ui_source))
    )

    observation = observer.observe()
    about = next(element for element in observation.elements if element.text.startswith("About"))

    assert about.clickable is True
    assert about.locator_strategy == "-android uiautomator"


def test_scroll_forward_translates_to_upward_finger_swipe() -> None:
    start, end = _scroll_path(ActionKind.SCROLL_FORWARD)

    assert start == (0.5, 0.8)
    assert end == (0.5, 0.2)


def _scenario() -> Scenario:
    return Scenario(
        scenario_id="open-about-phone",
        goal="Open About phone and show the device information",
        assertions=(VisibleTextAssertion("device-name", "Device name"),),
        allowed_actions=frozenset({ActionKind.TAP, ActionKind.SCROLL_FORWARD}),
        test_data={"account_password": "do-not-write"},
        max_steps=4,
    )


def _observation(
    root: Path,
    *,
    sequence: int,
    fingerprint: str,
    elements: tuple[ObservedElement, ...] = (),
) -> Observation:
    return Observation(
        sequence=sequence,
        fingerprint=fingerprint,
        screenshot=root / f"{sequence}.png",
        ui_source=root / f"{sequence}.xml",
        elements=elements,
        app_package="com.android.settings",
        activity=".Settings",
    )


class _QueuePlanner:
    def __init__(self, actions: list[PlannedAction]) -> None:
        self.actions = iter(actions)

    def decide(self, context: PlannerContext) -> PlannedAction:
        return next(self.actions)


class _SequenceObserver:
    def __init__(self, observations: list[Observation]) -> None:
        self.observations = iter(observations)

    def observe(self) -> Observation:
        return next(self.observations)


class _RecordingExecutor:
    def __init__(self) -> None:
        self.actions: list[PlannedAction] = []

    def execute(
        self,
        scenario: Scenario,
        action: PlannedAction,
        observation: Observation,
    ) -> ExecutionResult:
        self.actions.append(action)
        return ExecutionResult(operation=action.kind.value, elapsed_seconds=0.01)


class _Gateway:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response

    def choose_action(
        self,
        *,
        system_instruction: str,
        payload: Mapping[str, Any],
        screenshot: Path,
    ) -> Mapping[str, Any]:
        return self.response


class _Driver:
    current_package = "com.example"
    current_activity = ".MainActivity"


class _CaptureActions:
    def __init__(self, state: CapturedState) -> None:
        self.state = state
        self.driver = _Driver()

    def capture_state(self, label: str) -> CapturedState:
        return self.state
