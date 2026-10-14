"""Offline checks for Gemini cost and request boundaries."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import pytest

from agentic_mobile_test.gateways import (
    GeminiBudget,
    GeminiGateway,
    GeminiModelResponse,
    GeminiTokenUsage,
)
from agentic_mobile_test.agent.planner import (
    ModelGatewayUnavailableError,
    PlannerResponseError,
)


def test_gateway_sends_strict_bounded_request(tmp_path: Path) -> None:
    transport = _Transport(input_tokens=2_000)
    gateway = GeminiGateway(transport)
    screenshot = _screenshot(tmp_path)

    response = gateway.choose_action(
        system_instruction="Choose one action",
        payload={"goal": "Open About phone"},
        screenshot=screenshot,
    )

    assert response["action"] == "tap"
    assert transport.request["model"] == "gemini-3.5-flash-lite"
    assert transport.request["max_output_tokens"] == 200
    schema = transport.request["response_schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert gateway.usage.calls == 1
    assert gateway.usage.input_tokens == 2_000
    assert gateway.usage.output_tokens == 40
    assert gateway.usage.estimated_cost_usd == Decimal("0.000700")


def test_gateway_stops_at_call_limit(tmp_path: Path) -> None:
    gateway = GeminiGateway(
        _Transport(input_tokens=10),
        budget=GeminiBudget(max_calls=2),
    )
    screenshot = _screenshot(tmp_path)
    arguments = {
        "system_instruction": "Choose",
        "payload": {"goal": "Open"},
        "screenshot": screenshot,
    }

    gateway.choose_action(**arguments)
    gateway.choose_action(**arguments)
    with pytest.raises(ModelGatewayUnavailableError, match="call limit reached"):
        gateway.choose_action(**arguments)

    assert gateway.usage.calls == 2


def test_gateway_stops_before_request_when_cost_would_exceed_limit(
    tmp_path: Path,
) -> None:
    transport = _Transport(input_tokens=200_000)
    gateway = GeminiGateway(
        transport,
        budget=GeminiBudget(max_cost_usd=Decimal("0.001")),
    )

    with pytest.raises(ModelGatewayUnavailableError, match="cost limit"):
        gateway.choose_action(
            system_instruction="Choose",
            payload={"goal": "Open"},
            screenshot=_screenshot(tmp_path),
        )

    assert transport.generate_calls == 0
    assert gateway.usage.calls == 0


def test_gateway_rejects_non_object_response(tmp_path: Path) -> None:
    gateway = GeminiGateway(_Transport(input_tokens=10, value=["tap"]))

    with pytest.raises(PlannerResponseError, match="JSON object"):
        gateway.choose_action(
            system_instruction="Choose",
            payload={"goal": "Open"},
            screenshot=_screenshot(tmp_path),
        )


def test_gateway_requires_explicit_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ModelGatewayUnavailableError, match="GEMINI_API_KEY is not set"):
        GeminiGateway.from_environment()


class _Transport:
    def __init__(
        self,
        *,
        input_tokens: int,
        value: Any | None = None,
    ) -> None:
        self.input_tokens = input_tokens
        self.value = (
            value
            if value is not None
            else {
                "action": "tap",
                "target_ref": "e001",
                "value_ref": None,
                "reason": "The target matches the goal",
                "expected_effect": "The destination opens",
            }
        )
        self.generate_calls = 0
        self.request: dict[str, Any] = {}

    def count_tokens(
        self,
        *,
        model: str,
        system_instruction: str,
        payload: Mapping[str, Any],
        screenshot: Path,
    ) -> int:
        return self.input_tokens

    def generate_action(self, **request: Any) -> GeminiModelResponse:
        self.generate_calls += 1
        self.request = request
        return GeminiModelResponse(
            value=self.value,
            usage=GeminiTokenUsage(
                input_tokens=self.input_tokens,
                output_tokens=40,
            ),
        )


def _screenshot(root: Path) -> Path:
    path = root / "screen.png"
    path.write_bytes(b"fake-image-for-offline-contract-test")
    return path
