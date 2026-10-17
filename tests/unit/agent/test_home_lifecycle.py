"""Home checkpoints are selected before discovery and restored after errors."""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from agentic_mobile_test.contracts import Scenario, TextAssertion


def load_fixtures():
    path = Path(__file__).parents[2] / "autotests/ui/conftest.py"
    spec = importlib.util.spec_from_file_location("ui_fixture_contracts", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("fails", [False, True])
def test_home_setup_and_cleanup_even_after_test_error(tmp_path, monkeypatch, fails):
    fixtures = load_fixtures()
    calls = []
    device = SimpleNamespace()
    device.go_home = lambda: (calls.append("home") or SimpleNamespace(operation="go-home"))
    device.actions = SimpleNamespace(capture_state=lambda label: SimpleNamespace(
        screenshot=tmp_path / "s.png", ui_source=tmp_path / "s.xml"))
    device.driver = SimpleNamespace(current_package="launcher", current_activity=".Launcher")
    monkeypatch.setattr(fixtures.MobileDevice, "create", lambda *args, **kwargs: device)
    scenario = Scenario("home", "Check", (TextAssertion("x", "x"),),
                        start_screen="home", cleanup_screen="home")
    request = SimpleNamespace(fixturenames=["scenario"], getfixturevalue=lambda name: scenario,
                              module=SimpleNamespace(), node=SimpleNamespace())
    lifecycle = fixtures.android_settings_environment.__wrapped__(device.driver, tmp_path, request)
    environment = next(lifecycle)
    assert environment.setup_record["status"] == "ready"
    if fails:
        with pytest.raises(RuntimeError, match="test failed"):
            lifecycle.throw(RuntimeError("test failed"))
    else:
        with pytest.raises(StopIteration):
            next(lifecycle)
    assert calls == ["home", "home"]
    assert environment.cleanup_record["status"] == "ready"


def test_generated_replay_reads_checkpoints_from_scenario_file(tmp_path, monkeypatch):
    fixtures = load_fixtures()
    path = Path(__file__).parents[2] / "autotests/ui/android_settings/scenarios/artemis_accessibility_helper_enabled.json"
    calls = []
    device = SimpleNamespace(
        go_home=lambda: (calls.append("home") or SimpleNamespace(operation="go-home")),
        driver=SimpleNamespace(current_package="launcher", current_activity=".Launcher"),
        actions=SimpleNamespace(capture_state=lambda label: SimpleNamespace(
            screenshot=tmp_path / "s.png", ui_source=tmp_path / "s.xml")),
    )
    monkeypatch.setattr(fixtures.MobileDevice, "create", lambda *args, **kwargs: device)
    request = SimpleNamespace(fixturenames=[], module=SimpleNamespace(SCENARIO_PATH=path),
                              node=SimpleNamespace())
    lifecycle = fixtures.android_settings_environment.__wrapped__(device.driver, tmp_path, request)
    next(lifecycle)
    lifecycle.close()
    assert calls == ["home", "home"]
