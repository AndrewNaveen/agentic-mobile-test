"""Opt-in reconnaissance entry point, not a product regression test."""

from pathlib import Path
from decimal import Decimal
import json

import pytest

from agentic_mobile_test.agent.exploration import ExplorationBrief, ExplorationLoop, ExplorationPlanner, create_run_directory
from agentic_mobile_test.appium.actions import AppiumActions
from agentic_mobile_test.appium.executor import AppiumExecutor
from agentic_mobile_test.appium.observer import AppiumObserver
from agentic_mobile_test.gateways import GeminiBudget, GeminiGateway


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
    run_directory = create_run_directory(exploration_input, runs_directory)
    actions = AppiumActions(driver, evidence_dir=run_directory / "diagnostics")
    result = ExplorationLoop(
        planner=ExplorationPlanner(GeminiGateway.from_environment(budget=GeminiBudget(
            max_calls=exploration_input.max_steps, max_output_tokens=600,
            max_cost_usd=Decimal("0.02"),
        ))),
        reviewer=GeminiGateway.from_environment(budget=GeminiBudget(
            max_calls=1, max_output_tokens=1000, max_cost_usd=Decimal("0.02"),
        ), request_timeout_ms=60_000),
        observer=AppiumObserver(actions), executor=AppiumExecutor(actions),
    ).run(exploration_input, runs_directory=runs_directory, run_directory=run_directory)
    with capsys.disabled():
        print(f"Exploration report: {result.report_path.resolve()} ({result.status})")
        print(f"Exploration outcome: {result.summary}")
        report = json.loads(result.report_path.read_text(encoding="utf-8"))
        if "total_estimated_cost_usd" in report:
            print(f"Combined estimated cost: ${report['total_estimated_cost_usd']}")
        if any(report.get(key, {}).get("unaccounted_calls", 0) for key in ("model_usage", "review_usage")):
            print("Cost warning: failed requests have unknown usage; the estimate excludes them.")
        for review in report.get("completion_reviews", []):
            print(f"Final review: {review['status']}")
            if review["status"] == "returned":
                print(f"Review assessment: {review['response']['reason']}")
                for gap in review['response']['gaps']:
                    print(f"Review gap: {gap}")
            elif "error" in review:
                print(f"Review unavailable: {review['error']}")
        print(f"Manual cleanup required: {exploration_input.cleanup}")
    _report_exploration_outcome(result)


def _report_exploration_outcome(result):
    """Partial investigations are not product failures or successful regressions."""
    if result.status == "error":
        pytest.fail(f"Exploration harness error: {result.summary}\nReport: {result.report_path}", pytrace=False)
    if result.status in {"blocked", "needs_guidance", "budget_exhausted", "review_unavailable"}:
        pytest.skip(f"Exploration {result.status}: {result.summary}. Report: {result.report_path}")
    if result.status != "completed":
        pytest.fail(f"Unknown exploration status: {result.status}", pytrace=False)
