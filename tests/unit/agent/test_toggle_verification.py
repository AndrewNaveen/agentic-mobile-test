"""Offline checks for actual toggle state and non-mutating discovery."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentic_mobile_test.appium.observer import AppiumObserver
from agentic_mobile_test.agent.policy import ActionPolicy, PolicyViolation
from agentic_mobile_test.contracts import (
    ActionKind, PlannedAction, Scenario, TextAssertion, VerificationState,
)
from agentic_mobile_test.verification.verifier import TextVerifier


def observe(tmp_path, checked="true", duplicate=False):
    xml = tmp_path / "screen.xml"
    (tmp_path / "screen.png").write_bytes(b"stable screenshot")
    switch = '<node class="android.widget.Switch" resource-id="switch" checkable="true" checked="%s" clickable="true" enabled="true"/>' % checked
    xml.write_text('<hierarchy><node clickable="true"><node text="Use Artemis Accessibility Helper"/>'
                   + switch + (switch if duplicate else '') + '</node></hierarchy>')
    actions = SimpleNamespace(
        driver=SimpleNamespace(current_package="com.android.settings", current_activity=".Settings"),
        capture_state=lambda label: SimpleNamespace(ui_source=xml, screenshot=tmp_path / "screen.png"),
    )
    return AppiumObserver(actions, stable_seconds=0.001, poll_seconds=0.001).observe()


def scenario():
    return Scenario("helper", "Check without changing the service",
                    (TextAssertion("enabled", "Artemis Accessibility Helper", exact=False, checked=True),),
                    allow_toggle_changes=False)


@pytest.mark.parametrize("checked,expected", [
    ("true", VerificationState.PASSED),
    ("false", VerificationState.PRODUCT_FAILURE),
    ("unknown", VerificationState.PENDING),
])
def test_reads_checked_attribute_not_label(tmp_path, checked, expected):
    assert TextVerifier().evaluate(scenario(), observe(tmp_path, checked)).state is expected


def test_duplicate_switches_and_missing_controls_do_not_pass(tmp_path):
    observation = observe(tmp_path, duplicate=True)
    assert TextVerifier().evaluate(scenario(), observation).state is VerificationState.PENDING
    assert TextVerifier().evaluate(scenario(), replace(observation, elements=())).state is VerificationState.PENDING


def test_toggle_changes_change_fingerprint(tmp_path):
    assert observe(tmp_path, "true").fingerprint != observe(tmp_path, "false").fingerprint


def test_policy_blocks_switch_and_its_clickable_row_label(tmp_path):
    observation = observe(tmp_path)
    for element in observation.elements:
        if element.executable:
            action = PlannedAction(ActionKind.TAP, "try", "change", element.ref)
            with pytest.raises(PolicyViolation, match="forbids changing toggle"):
                ActionPolicy().validate(scenario=scenario(), action=action,
                                        observation=observation, history=(), step_number=1)


def test_scenario_json_loads_home_and_read_only_contract():
    path = Path(__file__).parents[2] / "autotests/ui/android_settings/scenarios/artemis_accessibility_helper_enabled.json"
    loaded = Scenario.load(path)
    assert loaded.start_screen == loaded.cleanup_screen == "home"
    assert loaded.allow_toggle_changes is False
    assert loaded.assertions[0].checked is True


@pytest.mark.parametrize("kwargs", [{"checked": "true"}, {"resource_id": "id"}])
def test_rejects_invalid_toggle_contract(kwargs):
    with pytest.raises(ValueError):
        TextAssertion("toggle", "label", **kwargs)


@pytest.mark.parametrize("field,value", [
    ("start_screen", "home"), ("cleanup_screen", "home"),
    ("allow_toggle_changes", True),
])
def test_generation_rejects_changed_lifecycle_or_policy(field, value):
    from agentic_mobile_test.evidence.artifacts import _jsonable, _scenario_record
    from agentic_mobile_test.generation.candidate import _scenario_matches
    original = scenario()
    record = _jsonable(_scenario_record(original))
    assert _scenario_matches(record, original)
    assert not _scenario_matches(record, replace(original, **{field: value}))


def test_generation_rejects_changed_toggle_expectation():
    from agentic_mobile_test.evidence.artifacts import _jsonable, _scenario_record
    from agentic_mobile_test.generation.candidate import _scenario_matches
    original = scenario()
    record = _jsonable(_scenario_record(original))
    changed = replace(original, assertions=(replace(original.assertions[0], checked=False),))
    assert not _scenario_matches(record, changed)
