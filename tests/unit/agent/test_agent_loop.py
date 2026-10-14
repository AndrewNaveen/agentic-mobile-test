"""Deterministic checks for the bounded agentic test architecture."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from agentic_mobile_test.appium.models import CapturedState
from agentic_mobile_test.appium.observer import AppiumObserver, _has_enabled_clickable_text
from agentic_mobile_test.appium.executor import AppiumExecutor, _scroll_path
from agentic_mobile_test.contracts import (
    ActionKind,
    ExecutionResult,
    Observation,
    ObservedElement,
    PlannedAction,
    RunOutcome,
    Scenario,
    ScenarioType,
    StepRecord,
    TextAssertion,
    TextExpectation,
)
from agentic_mobile_test.agent.planner import (
    PlannerContext,
    PlannerResponseError,
    StructuredPlanner,
)
from agentic_mobile_test.agent.planner import _planner_payload
from agentic_mobile_test.agent.policy import ActionPolicy, PolicyViolation
from agentic_mobile_test.device.platform import DeviceOperationResult
from agentic_mobile_test.agent.runner import AgentLoop
from agentic_mobile_test.verification.verifier import TextVerifier


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
        verifier=TextVerifier(),
    )

    result = loop.run(_scenario(), runs_directory=tmp_path / "runs")

    assert result.outcome is RunOutcome.PASSED
    assert len(result.steps) == 1
    assert executor.actions == [action]
    assert result.run_directory is not None
    assert (result.run_directory / "scenario.json").is_file()
    assert (result.run_directory / "steps.jsonl").is_file()
    assert (result.run_directory / "result.json").is_file()
    assert (result.run_directory / "discovered-path.json").is_file()
    scenario_artifact = (result.run_directory / "scenario.json").read_text(encoding="utf-8")
    assert "account_password" in scenario_artifact
    assert "do-not-write" not in scenario_artifact
    discovery = json.loads(
        (result.run_directory / "discovered-path.json").read_text(encoding="utf-8")
    )
    assert discovery["record_type"] == "successful_ui_path"
    assert discovery["generation_status"] == "candidate_requires_review"
    assert discovery["scenario"]["scenario_type"] == "positive"
    assert discovery["steps"][0]["action"]["target"]["label"] == "About phone"
    assert discovery["steps"][0]["transition"]["screen_changed"] is True
    assert discovery["steps"][0]["transition"]["before"]["screenshot_sha256"]
    for step in discovery["steps"]:
        for phase in ("before", "after"):
            for kind in ("screenshot", "ui_source"):
                relative = Path(step["transition"][phase][kind])
                staged = (result.run_directory / relative).resolve()
                assert staged.is_relative_to(result.run_directory.resolve())
                assert staged.is_file()
    assert "do-not-write" not in json.dumps(discovery)


def test_agent_loop_does_required_tap_even_if_final_text_is_already_visible(
    tmp_path: Path,
) -> None:
    scenario = Scenario.from_mapping(
        {
            "schema_version": 1,
            "scenario_id": "retry-action",
            "scenario_type": "edge",
            "goal": "Tap Retry on the offline screen",
            "preconditions": [],
            "cleanup": [],
            "assertions": [{"assertion_id": "offline", "text": "Connect to the internet"}],
            "allowed_actions": ["tap"],
            "test_data": {},
            "launchable_apps": {},
            "required_interactions": [{"action": "tap", "target_text": "Retry"}],
            "max_steps": 2,
        }
    )
    visible_screen = _observation(
        tmp_path,
        sequence=1,
        fingerprint="youtube-offline",
        elements=(
            ObservedElement(ref="e001", label="Connect to the internet", text="Connect to the internet"),
            ObservedElement(
                ref="e002",
                label="Retry",
                text="Retry",
                clickable=True,
                enabled=True,
                locator_strategy="accessibility id",
                locator_value="Retry",
            ),
        ),
    )
    after_tap = _observation(
        tmp_path,
        sequence=2,
        fingerprint="youtube-offline-after-retry",
        elements=visible_screen.elements,
    )
    retry_action = PlannedAction(
        kind=ActionKind.TAP,
        target_ref="e002",
        reason="Retry is enabled and requested by the scenario",
        expected_effect="YouTube retries its connection",
    )

    result = AgentLoop(
        planner=_QueuePlanner([retry_action]),
        observer=_SequenceObserver([visible_screen, after_tap]),
        policy=ActionPolicy(),
        executor=_RecordingExecutor(),
        verifier=TextVerifier(),
    ).run(scenario)

    assert result.outcome is RunOutcome.PASSED
    assert len(result.steps) == 1
    assert result.steps[0].before.element("e002").enabled is True


@pytest.mark.parametrize("scenario_type", list(ScenarioType))
def test_scenario_contract_accepts_positive_negative_and_edge(
    scenario_type: ScenarioType,
) -> None:
    scenario = Scenario.from_mapping(
        {
            "schema_version": 1,
            "scenario_id": f"example-{scenario_type.value}",
            "scenario_type": scenario_type.value,
            "goal": "Exercise one reviewed Android Settings behavior",
            "preconditions": ["Settings is at its root screen"],
            "cleanup": ["Return Settings to its root screen"],
            "assertions": [{"assertion_id": "result", "text": "Expected result"}],
            "allowed_actions": ["tap"],
            "test_data": {},
            "launchable_apps": {},
            "max_steps": 3,
        }
    )

    assert scenario.scenario_type is scenario_type
    assert scenario.preconditions
    assert scenario.cleanup


def test_scenario_contract_rejects_unknown_fields() -> None:
    document = {
        "schema_version": 1,
        "scenario_id": "unknown-field",
        "scenario_type": "positive",
        "goal": "Example",
        "preconditions": [],
        "cleanup": [],
        "assertions": [{"assertion_id": "result", "text": "Expected"}],
        "allowed_actions": ["tap"],
        "test_data": {},
        "launchable_apps": {},
        "max_steps": 3,
        "planner_can_change_assertions": True,
    }

    with pytest.raises(ValueError, match="unknown"):
        Scenario.from_mapping(document)


def test_scenario_contract_keeps_app_allowlist_optional_for_existing_scenarios() -> None:
    scenario = Scenario.from_mapping(
        {
            "schema_version": 1,
            "scenario_id": "settings-screen",
            "scenario_type": "positive",
            "goal": "Open a Settings screen",
            "preconditions": [],
            "cleanup": [],
            "assertions": [{"assertion_id": "screen", "text": "Settings"}],
            "allowed_actions": ["tap"],
            "test_data": {},
            "max_steps": 2,
        }
    )

    assert scenario.launchable_apps == {}


def test_scenario_contract_loads_required_interactions() -> None:
    scenario = Scenario.from_mapping(
        {
            "schema_version": 1,
            "scenario_id": "retry-required",
            "scenario_type": "positive",
            "goal": "Retry the request",
            "preconditions": [],
            "cleanup": [],
            "assertions": [{"assertion_id": "offline", "text": "Retry"}],
            "allowed_actions": ["tap"],
            "test_data": {},
            "required_interactions": [
                {"action": "tap", "target_text": "Retry", "minimum_count": 1}
            ],
            "max_steps": 2,
        }
    )

    assert scenario.required_interactions[0].action is ActionKind.TAP
    assert scenario.required_interactions[0].target_text == "Retry"


def test_absence_assertion_is_a_deterministic_negative_oracle(tmp_path: Path) -> None:
    scenario = Scenario(
        scenario_id="settings-denies-unavailable-device",
        goal="Show that an unavailable device was not added",
        assertions=(
            TextAssertion(
                "device-not-added",
                "Added successfully",
                expectation=TextExpectation.ABSENT,
            ),
        ),
        allowed_actions=frozenset({ActionKind.TAP}),
    )
    observation = _observation(
        tmp_path,
        sequence=1,
        fingerprint="settings-error",
        elements=(ObservedElement(ref="e001", label="Device unavailable"),),
    )

    result = TextVerifier().evaluate(scenario, observation)

    assert result.state.value == "passed"
    assert result.checks[0].passed is True
    assert "Confirmed text is absent" in result.checks[0].detail


def test_absence_assertion_fails_when_unwanted_text_is_present(tmp_path: Path) -> None:
    scenario = Scenario(
        scenario_id="settings-denies-unavailable-device",
        goal="Show that an unavailable device was not added",
        assertions=(
            TextAssertion(
                "device-not-added",
                "Added successfully",
                expectation=TextExpectation.ABSENT,
            ),
        ),
        allowed_actions=frozenset({ActionKind.TAP}),
    )
    observation = _observation(
        tmp_path,
        sequence=1,
        fingerprint="settings-unexpected-success",
        elements=(ObservedElement(ref="e001", label="Added successfully"),),
    )

    result = TextVerifier().evaluate(scenario, observation)

    assert result.state.value == "pending"
    assert result.checks[0].passed is False
    assert "Unexpected text is visible" in result.checks[0].detail


def test_absence_scenario_cannot_pass_before_executing_an_action(tmp_path: Path) -> None:
    scenario = Scenario(
        scenario_id="settings-denies-unavailable-device",
        goal="Attempt the unavailable-device flow and ensure it is not added",
        assertions=(
            TextAssertion(
                "success-message-absent",
                "Added successfully",
                expectation=TextExpectation.ABSENT,
            ),
        ),
        allowed_actions=frozenset({ActionKind.TAP}),
        max_steps=1,
    )
    initial = _observation(
        tmp_path,
        sequence=1,
        fingerprint="settings-root",
        elements=(
            ObservedElement(
                ref="e001",
                label="Add device",
                text="Add device",
                clickable=True,
                locator_strategy="accessibility id",
                locator_value="Add device",
            ),
        ),
    )
    after_action = _observation(
        tmp_path,
        sequence=2,
        fingerprint="settings-error",
        elements=(ObservedElement(ref="e001", label="Device unavailable"),),
    )

    result = AgentLoop(
        planner=_QueuePlanner(
            [
                PlannedAction(
                    kind=ActionKind.TAP,
                    target_ref="e001",
                    reason="Start the reviewed negative flow",
                    expected_effect="Show the unavailable-device response",
                )
            ]
        ),
        observer=_SequenceObserver([initial, after_action]),
        policy=ActionPolicy(),
        executor=_RecordingExecutor(),
        verifier=TextVerifier(),
    ).run(scenario)

    assert result.outcome is RunOutcome.PASSED
    assert len(result.steps) == 1


def test_unsatisfied_run_does_not_create_discovered_path(tmp_path: Path) -> None:
    before = _observation(
        tmp_path,
        sequence=1,
        fingerprint="settings-root",
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
    after = _observation(
        tmp_path,
        sequence=2,
        fingerprint="settings-root",
        elements=before.elements,
    )
    action = PlannedAction(
        kind=ActionKind.TAP,
        target_ref="e001",
        reason="Try the visible destination",
        expected_effect="Open About phone",
    )
    result = AgentLoop(
        planner=_QueuePlanner([action]),
        observer=_SequenceObserver([before, after]),
        policy=ActionPolicy(),
        executor=_RecordingExecutor(),
        verifier=TextVerifier(),
    ).run(_scenario(), runs_directory=tmp_path / "failed-runs")

    assert result.outcome is RunOutcome.TEST_FAILURE
    assert result.run_directory is not None
    assert (result.run_directory / "result.json").is_file()
    assert not (result.run_directory / "discovered-path.json").exists()


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


def test_wait_predicate_requires_enabled_clickable_target() -> None:
    assert _has_enabled_clickable_text(
        '<root><node text="RETRY" clickable="true" enabled="true" /></root>',
        "retry",
    )
    assert not _has_enabled_clickable_text(
        '<root><node text="RETRY" clickable="false" enabled="true" /></root>',
        "retry",
    )
    assert not _has_enabled_clickable_text(
        '<root><node text="RETRY" clickable="true" enabled="false" /></root>',
        "retry",
    )


def test_scroll_forward_translates_to_upward_finger_swipe() -> None:
    start, end = _scroll_path(ActionKind.SCROLL_FORWARD)

    assert start == (0.5, 0.8)
    assert end == (0.5, 0.2)


def test_launch_app_requires_scenario_approved_reference(tmp_path: Path) -> None:
    scenario = Scenario(
        scenario_id="launch-youtube",
        goal="Open YouTube",
        assertions=(TextAssertion("offline", "Connect to the internet"),),
        allowed_actions=frozenset({ActionKind.LAUNCH_APP}),
        launchable_apps={"youtube": "com.google.android.youtube"},
    )
    observation = _observation(tmp_path, sequence=1, fingerprint="settings")
    action = PlannedAction(
        kind=ActionKind.LAUNCH_APP,
        value_ref="youtube",
        reason="Continue in YouTube",
        expected_effect="YouTube opens",
    )

    ActionPolicy().validate(
        scenario=scenario,
        action=action,
        observation=observation,
        history=(),
        step_number=1,
    )
    payload = _planner_payload(
        PlannerContext(scenario, observation, history=(), remaining_steps=1)
    )
    assert payload["approved_apps"] == [
        {"ref": "youtube", "app_id": "com.google.android.youtube"}
    ]

    unapproved = PlannedAction(
        kind=ActionKind.LAUNCH_APP,
        value_ref="com.example.unknown",
        reason="Try another app",
        expected_effect="Unknown app opens",
    )
    with pytest.raises(PolicyViolation, match="approved app"):
        ActionPolicy().validate(
            scenario=scenario,
            action=unapproved,
            observation=observation,
            history=(),
            step_number=1,
        )


def test_appium_executor_launches_only_the_mapped_package(tmp_path: Path) -> None:
    class Apps:
        launched: list[str] = []

        def launch(self, app_id: str) -> DeviceOperationResult:
            self.launched.append(app_id)
            return DeviceOperationResult("launch-app", 0.1, {"app_id": app_id})

    apps = Apps()
    scenario = Scenario(
        scenario_id="launch-youtube",
        goal="Open YouTube",
        assertions=(TextAssertion("offline", "Connect to the internet"),),
        allowed_actions=frozenset({ActionKind.LAUNCH_APP}),
        launchable_apps={"youtube": "com.google.android.youtube"},
    )
    action = PlannedAction(
        kind=ActionKind.LAUNCH_APP,
        value_ref="youtube",
        reason="Continue in YouTube",
        expected_effect="YouTube opens",
    )

    result = AppiumExecutor(_NoopActions(), apps=apps).execute(
        scenario,
        action,
        _observation(tmp_path, sequence=1, fingerprint="settings"),
    )

    assert apps.launched == ["com.google.android.youtube"]
    assert result.operation == "launch-app"


class _NoopActions:
    """Unused low-level action placeholder for testing a device-app launch."""


def _scenario() -> Scenario:
    return Scenario(
        scenario_id="open-about-phone",
        goal="Open About phone and show the device information",
        assertions=(TextAssertion("device-name", "Device name"),),
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
    screenshot = root / f"{sequence}.png"
    ui_source = root / f"{sequence}.xml"
    screenshot.write_bytes(f"screenshot-{sequence}".encode())
    ui_source.write_text("<hierarchy />", encoding="utf-8")
    return Observation(
        sequence=sequence,
        fingerprint=fingerprint,
        screenshot=screenshot,
        ui_source=ui_source,
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
