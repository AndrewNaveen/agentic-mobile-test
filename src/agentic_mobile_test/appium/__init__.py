"""Deterministic Appium interactions used by pytest tests."""

from .actions import AppiumActions
from .executor import AppiumExecutor
from .models import (
    ActionEvidence,
    ActionResult,
    AppiumActionError,
    CapturedState,
    Locator,
    OverlayRule,
    Point,
    Rect,
    SliderResult,
    SliderValueUnavailableError,
)
from .targets import (
    AppiumTargetResolver,
    LocatorCandidate,
    LocatorResolutionError,
    ResolvedTarget,
    SemanticTarget,
    TargetCatalog,
    TargetCatalogError,
)

__all__ = [
    "ActionEvidence",
    "ActionResult",
    "AppiumActionError",
    "AppiumActions",
    "AppiumExecutor",
    "AppiumTargetResolver",
    "CapturedState",
    "Locator",
    "LocatorCandidate",
    "LocatorResolutionError",
    "OverlayRule",
    "Point",
    "Rect",
    "ResolvedTarget",
    "SemanticTarget",
    "SliderResult",
    "SliderValueUnavailableError",
    "TargetCatalog",
    "TargetCatalogError",
]
