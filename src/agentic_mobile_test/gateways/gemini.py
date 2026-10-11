"""Cost-bounded Gemini implementation of the planner model gateway."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Any, Mapping, Protocol

from ..planner import ModelGatewayUnavailableError, PlannerResponseError

_ACTION_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "action",
        "target_ref",
        "value_ref",
        "reason",
        "expected_effect",
    ],
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "tap",
                "type_text",
                "scroll_forward",
                "scroll_backward",
                "press_back",
            ],
        },
        "target_ref": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "value_ref": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "reason": {"type": "string"},
        "expected_effect": {"type": "string"},
    },
}


@dataclass(frozen=True)
class GeminiBudget:
    model: str = "gemini-3.5-flash-lite"
    max_calls: int = 10
    max_output_tokens: int = 200
    max_cost_usd: Decimal = Decimal("0.02")
    input_usd_per_million_tokens: Decimal = Decimal("0.30")
    output_usd_per_million_tokens: Decimal = Decimal("2.50")

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("Gemini model cannot be empty")
        if self.max_calls <= 0:
            raise ValueError("max_calls must be greater than zero")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be greater than zero")
        if self.max_cost_usd <= 0:
            raise ValueError("max_cost_usd must be greater than zero")
        if self.input_usd_per_million_tokens < 0:
            raise ValueError("input token price cannot be negative")
        if self.output_usd_per_million_tokens < 0:
            raise ValueError("output token price cannot be negative")


@dataclass(frozen=True)
class GeminiTokenUsage:
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("Token usage cannot be negative")


@dataclass(frozen=True)
class GeminiModelResponse:
    value: Mapping[str, Any]
    usage: GeminiTokenUsage


@dataclass(frozen=True)
class GeminiGatewayUsage:
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal


class GeminiTransport(Protocol):
    def count_tokens(
        self,
        *,
        model: str,
        system_instruction: str,
        payload: Mapping[str, Any],
        screenshot: Path,
    ) -> int: ...

    def generate_action(
        self,
        *,
        model: str,
        system_instruction: str,
        payload: Mapping[str, Any],
        screenshot: Path,
        max_output_tokens: int,
        response_schema: Mapping[str, Any],
    ) -> GeminiModelResponse: ...


class GeminiGateway:
    """Enforce local limits before delegating one decision to Gemini."""

    def __init__(
        self,
        transport: GeminiTransport,
        *,
        budget: GeminiBudget = GeminiBudget(),
    ) -> None:
        self.transport = transport
        self.budget = budget
        self._calls = 0
        self._input_tokens = 0
        self._output_tokens = 0

    @classmethod
    def from_environment(
        cls,
        *,
        budget: GeminiBudget = GeminiBudget(),
    ) -> "GeminiGateway":
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ModelGatewayUnavailableError(
                "GEMINI_API_KEY is not set; the paid model experiment was not started"
            )
        return cls(_GoogleGenAITransport(api_key), budget=budget)

    @property
    def usage(self) -> GeminiGatewayUsage:
        return GeminiGatewayUsage(
            calls=self._calls,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            estimated_cost_usd=self._cost(
                self._input_tokens,
                self._output_tokens,
            ),
        )

    def choose_action(
        self,
        *,
        system_instruction: str,
        payload: Mapping[str, Any],
        screenshot: Path,
    ) -> Mapping[str, Any]:
        if self._calls >= self.budget.max_calls:
            raise ModelGatewayUnavailableError(
                f"Gemini call limit reached ({self.budget.max_calls})"
            )
        if not screenshot.is_file():
            raise ModelGatewayUnavailableError(
                f"Planner screenshot is unavailable: {screenshot}"
            )

        try:
            predicted_input_tokens = self.transport.count_tokens(
                model=self.budget.model,
                system_instruction=system_instruction,
                payload=payload,
                screenshot=screenshot,
            )
        except Exception as error:
            raise _unavailable("Gemini token preflight failed", error) from error
        if predicted_input_tokens < 0:
            raise PlannerResponseError("Gemini returned a negative token count")

        projected_cost = self._cost(
            self._input_tokens + predicted_input_tokens,
            self._output_tokens + self.budget.max_output_tokens,
        )
        if projected_cost > self.budget.max_cost_usd:
            raise ModelGatewayUnavailableError(
                "Gemini cost limit would be exceeded: "
                f"projected ${projected_cost:.6f}, "
                f"limit ${self.budget.max_cost_usd:.6f}"
            )

        self._calls += 1
        try:
            response = self.transport.generate_action(
                model=self.budget.model,
                system_instruction=system_instruction,
                payload=payload,
                screenshot=screenshot,
                max_output_tokens=self.budget.max_output_tokens,
                response_schema=_ACTION_SCHEMA,
            )
        except Exception as error:
            raise _unavailable("Gemini action request failed", error) from error

        self._input_tokens += response.usage.input_tokens
        self._output_tokens += response.usage.output_tokens
        if not isinstance(response.value, Mapping):
            raise PlannerResponseError("Gemini response must be a JSON object")
        return dict(response.value)

    def _cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        million = Decimal(1_000_000)
        return (
            Decimal(input_tokens) * self.budget.input_usd_per_million_tokens
            + Decimal(output_tokens) * self.budget.output_usd_per_million_tokens
        ) / million


class _GoogleGenAITransport:
    """Small SDK boundary configured for one attempt and structured JSON."""

    def __init__(self, api_key: str) -> None:
        try:
            from google import genai
            from google.genai import types
        except ImportError as error:
            raise ModelGatewayUnavailableError(
                "Gemini support is not installed; run "
                "python -m pip install -e '.[gemini]'"
            ) from error

        self._types = types
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=30_000,
                # attempts includes the initial request, so 1 means no retries.
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    def count_tokens(
        self,
        *,
        model: str,
        system_instruction: str,
        payload: Mapping[str, Any],
        screenshot: Path,
    ) -> int:
        response = self._client.models.count_tokens(
            model=model,
            # Gemini Developer API count_tokens does not accept
            # CountTokensConfig.system_instruction. Count the same text as an
            # ordinary content part so the local cost preflight remains
            # conservative without changing the generation request.
            contents=self._contents(
                payload,
                screenshot,
                prefix=system_instruction,
            ),
        )
        return int(response.total_tokens or 0)

    def generate_action(
        self,
        *,
        model: str,
        system_instruction: str,
        payload: Mapping[str, Any],
        screenshot: Path,
        max_output_tokens: int,
        response_schema: Mapping[str, Any],
    ) -> GeminiModelResponse:
        response = self._client.models.generate_content(
            model=model,
            contents=self._contents(payload, screenshot),
            config=self._types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=max_output_tokens,
                response_mime_type="application/json",
                response_json_schema=dict(response_schema),
                thinking_config=self._types.ThinkingConfig(
                    thinking_level="minimal"
                ),
            ),
        )
        value = response.parsed
        if value is None:
            try:
                value = json.loads(response.text or "")
            except json.JSONDecodeError as error:
                raise PlannerResponseError("Gemini returned invalid JSON") from error
        usage = response.usage_metadata
        return GeminiModelResponse(
            value=value,
            usage=GeminiTokenUsage(
                input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
                output_tokens=int(
                    (getattr(usage, "candidates_token_count", 0) or 0)
                    + (getattr(usage, "thoughts_token_count", 0) or 0)
                ),
            ),
        )

    def _contents(
        self,
        payload: Mapping[str, Any],
        screenshot: Path,
        *,
        prefix: str | None = None,
    ) -> list[Any]:
        mime_type = _image_mime_type(screenshot)
        contents: list[Any] = []
        if prefix:
            contents.append(prefix)
        contents.extend([
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            self._types.Part.from_bytes(
                data=screenshot.read_bytes(),
                mime_type=mime_type,
            ),
        ])
        return contents


def _image_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    try:
        return mime_types[suffix]
    except KeyError as error:
        raise ModelGatewayUnavailableError(
            f"Unsupported planner screenshot format: {suffix or '<none>'}"
        ) from error


def _unavailable(message: str, error: Exception) -> ModelGatewayUnavailableError:
    code = getattr(error, "code", None)
    suffix = f" (HTTP {code})" if code is not None else ""
    return ModelGatewayUnavailableError(f"{message}{suffix}: {type(error).__name__}")
