"""Explicitly enabled, cost-bounded Gemini connection check."""

from __future__ import annotations

import base64
from decimal import Decimal
from pathlib import Path

import pytest

from agentic_mobile_test.contracts import (
    ActionKind,
    Observation,
    ObservedElement,
    Scenario,
    TextAssertion,
)
from agentic_mobile_test.gateways import GeminiBudget, GeminiGateway
from agentic_mobile_test.agent.planner import PlannerContext, StructuredPlanner

_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


@pytest.mark.gemini
def test_gemini_returns_one_structured_bounded_action(tmp_path: Path) -> None:
    """Spend at most $0.001 to verify credentials, model, and JSON schema."""

    screenshot = tmp_path / "observation.png"
    screenshot.write_bytes(_ONE_PIXEL_PNG)
    gateway = GeminiGateway.from_environment(
        budget=GeminiBudget(
            max_calls=1,
            max_output_tokens=200,
            max_cost_usd=Decimal("0.001"),
        )
    )
    planner = StructuredPlanner(gateway)
    scenario = Scenario(
        scenario_id="gemini-connection-check",
        goal="Tap the visible About phone element",
        assertions=(TextAssertion("destination", "Device name"),),
        allowed_actions=frozenset({ActionKind.TAP}),
        max_steps=1,
    )
    observation = Observation(
        sequence=1,
        fingerprint="connection-check",
        screenshot=screenshot,
        ui_source=tmp_path / "observation.xml",
        elements=(
            ObservedElement(
                ref="e001",
                label="About phone",
                text="About phone",
                clickable=True,
                enabled=True,
            ),
        ),
        app_package="com.android.settings",
        activity=".Settings",
    )

    action = planner.decide(
        PlannerContext(
            scenario=scenario,
            observation=observation,
            history=(),
            remaining_steps=1,
        )
    )

    assert action.kind is ActionKind.TAP
    assert action.target_ref == "e001"
    assert gateway.usage.calls == 1
    assert gateway.usage.estimated_cost_usd <= Decimal("0.001")
