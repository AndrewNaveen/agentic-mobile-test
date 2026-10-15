"""Transition frames must never be accepted as planner observations."""

from types import SimpleNamespace

import pytest

from agentic_mobile_test.appium.observer import AppiumObserver, ObservationError


class Frames:
    def __init__(self, tmp_path, frames):
        self.directory = tmp_path
        self.frames = iter(frames)
        self.last = None
        self.calls = 0
        self.driver = SimpleNamespace(current_package="settings", current_activity=".Settings")

    def capture_state(self, label):
        self.calls += 1
        self.last = next(self.frames, self.last)
        image, xml = self.last
        screenshot = self.directory / f"{label}.png"
        source = self.directory / f"{label}.xml"
        screenshot.write_bytes(image)
        source.write_text(xml)
        return SimpleNamespace(screenshot=screenshot, ui_source=source)


def observer(actions, timeout=0.1):
    return AppiumObserver(actions, stable_seconds=0.005,
                          poll_seconds=0.002, settle_timeout_seconds=timeout)


def test_image_transition_with_already_stable_xml_is_rejected(tmp_path):
    xml = '<hierarchy><node text="Settings" /></hierarchy>'
    actions = Frames(tmp_path, [(b"splash", xml), (b"fading", xml), (b"ready", xml)])
    observation = observer(actions).observe()
    assert observation.screenshot.read_bytes() == b"ready"
    assert actions.calls >= 4
    assert observation.elements[0].text == "Settings"


def test_stable_image_with_changing_hierarchy_is_rejected(tmp_path):
    actions = Frames(tmp_path, [(b"same", '<hierarchy><node text="old" /></hierarchy>'),
                                (b"same", '<hierarchy><node text="new" /></hierarchy>')])
    assert observer(actions).observe().elements[0].text == "new"
    assert actions.calls >= 3


def test_never_settling_screen_has_bounded_failure_and_diagnostic_path(tmp_path):
    actions = Frames(tmp_path, ((str(i).encode(), '<hierarchy/>') for i in range(1000)))
    with pytest.raises(ObservationError, match="no transition frame.*Last capture"):
        observer(actions, timeout=0.02).observe()
    assert actions.calls < 1000


def test_malformed_xml_is_not_a_valid_observation(tmp_path):
    with pytest.raises(ObservationError, match="Unable to read observation"):
        observer(Frames(tmp_path, [(b"image", '<broken')])).observe()


def test_package_transition_during_capture_resets_stability(tmp_path):
    actions = Frames(tmp_path, [(b"same", '<hierarchy/>')])
    capture = actions.capture_state
    def changing_capture(label):
        state = capture(label)
        if actions.calls == 2:
            actions.driver.current_package = "new.package"
        return state
    actions.capture_state = changing_capture
    result = observer(actions).observe()
    assert result.app_package == "new.package"
    assert actions.calls >= 4


@pytest.mark.parametrize("kwargs", [
    {"stable_seconds": 0}, {"settle_timeout_seconds": 0.5}, {"poll_seconds": 0},
])
def test_invalid_wait_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        AppiumObserver(None, **kwargs)
