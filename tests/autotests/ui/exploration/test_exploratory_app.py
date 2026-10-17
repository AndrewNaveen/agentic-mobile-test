"""Opt-in reconnaissance entry point, not a product regression test."""

from pathlib import Path
from uuid import uuid4

import pytest

from agentic_mobile_test.agent.exploration import ExplorationBrief, ExplorationLoop, ExplorationPlanner
from agentic_mobile_test.appium.actions import AppiumActions
from agentic_mobile_test.appium.executor import AppiumExecutor
from agentic_mobile_test.appium.observer import AppiumObserver
from agentic_mobile_test.gateways import GeminiGateway


@pytest.fixture
def exploration_input(request):
    path = request.config.getoption("exploration_brief")
    if not path:
        pytest.skip("Pass --exploration-brief to explicitly select an exploration")
    brief = ExplorationBrief.load(Path(path))
    config = request.getfixturevalue("appium_config")
    if config.app_package != brief.app_package or not config.no_reset:
        pytest.fail("Exploration requires matching --appium-package and --appium-no-reset")
    return brief


@pytest.mark.appium
@pytest.mark.gemini
def test_explore_app(exploration_input, request, runs_directory, capsys):
    # Resolve driver only after validating explicit exploration opt-in.
    driver = request.getfixturevalue("driver")
    actions = AppiumActions(driver, evidence_dir=runs_directory / f"exploration-captures-{uuid4().hex[:8]}")
    result = ExplorationLoop(
        planner=ExplorationPlanner(GeminiGateway.from_environment()),
        observer=AppiumObserver(actions), executor=AppiumExecutor(actions),
    ).run(exploration_input, runs_directory=runs_directory)
    with capsys.disabled():
        print(f"Exploration report: {result.report_path.resolve()} ({result.status})")
        print(f"Manual cleanup required: {exploration_input.cleanup}")
    # This checks the exploration harness only, NOT product correctness or coverage.
    assert result.status in {"completed", "needs_guidance", "budget_exhausted"}, result.summary
