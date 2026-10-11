"""Small data types shared by the Appium action layer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias

Locator: TypeAlias = tuple[str, str]


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @classmethod
    def from_element(cls, element: Any) -> Rect:
        rect = element.rect
        return cls(
            x=round(rect["x"]),
            y=round(rect["y"]),
            width=round(rect["width"]),
            height=round(rect["height"]),
        )

    def point_at(self, x_percent: float, y_percent: float) -> Point:
        if not 0 <= x_percent <= 100 or not 0 <= y_percent <= 100:
            raise ValueError("Element offsets must be between 0 and 100 percent")
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"Element has invalid bounds: {self}")
        return Point(
            x=round(self.x + (self.width - 1) * x_percent / 100),
            y=round(self.y + (self.height - 1) * y_percent / 100),
        )


@dataclass(frozen=True)
class CapturedState:
    screenshot: Path
    ui_source: Path


@dataclass(frozen=True)
class ActionEvidence:
    before: CapturedState | None = None
    after: CapturedState | None = None
    failure: CapturedState | None = None


@dataclass(frozen=True)
class ActionResult:
    operation: str
    elapsed_seconds: float
    details: Mapping[str, Any] = field(default_factory=dict)
    evidence: ActionEvidence = field(default_factory=ActionEvidence)


@dataclass(frozen=True)
class SliderResult:
    action: ActionResult
    target_percent: float
    ui_percent: float | None
    independent_percent: float | None
    attempts: int


@dataclass(frozen=True)
class OverlayRule:
    """A known overlay and the control that closes it, when one exists."""

    container: Locator
    dismiss: Locator | None = None
    timeout_seconds: float = 2.0


class AppiumActionError(RuntimeError):
    """An interaction failed and should fail the calling pytest test."""

    def __init__(
        self,
        operation: str,
        message: str,
        *,
        evidence: CapturedState | None = None,
    ) -> None:
        suffix = f" Evidence: {evidence.screenshot.parent}" if evidence else ""
        super().__init__(f"{operation} failed: {message}.{suffix}")
        self.operation = operation
        self.evidence = evidence


class SliderValueUnavailableError(ValueError):
    """The slider exposes no numeric value that can be verified."""
