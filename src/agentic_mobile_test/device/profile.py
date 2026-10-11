"""Device identity and live geometry derived from an Appium session."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class MobilePlatform(StrEnum):
    ANDROID = "android"
    IOS = "ios"

    @classmethod
    def parse(cls, value: object) -> "MobilePlatform":
        normalized = str(value or "").strip().lower()
        if normalized == "android":
            return cls.ANDROID
        if normalized in {"ios", "iphone", "iphoneos"}:
            return cls.IOS
        raise ValueError(f"Unsupported mobile platform: {value!r}")


@dataclass(frozen=True)
class DeviceProfile:
    """Stable device/session identity; no hard-coded supported-version table."""

    platform: MobilePlatform
    model: str
    os_version: str
    identifier: str

    @classmethod
    def from_driver(cls, driver: Any) -> "DeviceProfile":
        capabilities = _capabilities(driver)
        return cls(
            platform=MobilePlatform.parse(
                _capability(capabilities, "platformName", "platform")
            ),
            model=_text(
                _capability(
                    capabilities,
                    "appium:deviceModel",
                    "deviceModel",
                    "appium:deviceName",
                    "deviceName",
                ),
                fallback="unknown",
            ),
            os_version=_text(
                _capability(
                    capabilities,
                    "appium:platformVersion",
                    "platformVersion",
                ),
                fallback="unknown",
            ),
            identifier=_text(
                _capability(
                    capabilities,
                    "appium:udid",
                    "udid",
                    "appium:deviceUDID",
                    "deviceUDID",
                ),
                fallback="unknown",
            ),
        )

    @property
    def is_android(self) -> bool:
        return self.platform is MobilePlatform.ANDROID

    @property
    def is_ios(self) -> bool:
        return self.platform is MobilePlatform.IOS


@dataclass(frozen=True)
class Viewport:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0:
            raise ValueError("Viewport origin cannot be negative")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Viewport width and height must be positive")


@dataclass(frozen=True)
class DeviceGeometry:
    """A runtime snapshot that may change after rotation or window resizing."""

    width: int
    height: int
    orientation: str
    pixel_ratio: float | None
    viewport: Viewport

    @classmethod
    def from_driver(cls, driver: Any) -> "DeviceGeometry":
        size = driver.get_window_size()
        width = _positive_integer(size.get("width"), "window width")
        height = _positive_integer(size.get("height"), "window height")
        capabilities = _capabilities(driver)
        viewport = _viewport(capabilities, width, height)
        orientation = _orientation(driver)
        pixel_ratio = _positive_float(
            _capability(capabilities, "appium:pixelRatio", "pixelRatio")
        )
        return cls(
            width=width,
            height=height,
            orientation=orientation,
            pixel_ratio=pixel_ratio,
            viewport=viewport,
        )


def _capabilities(driver: Any) -> Mapping[str, Any]:
    capabilities = getattr(driver, "capabilities", {})
    if not isinstance(capabilities, Mapping):
        raise ValueError("Appium driver capabilities must be a mapping")
    return capabilities


def _capability(capabilities: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = capabilities.get(name)
        if value is not None and str(value).strip():
            return value
    return None


def _text(value: object, *, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _positive_integer(value: object, name: str) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an integer") from error
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _positive_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _viewport(
    capabilities: Mapping[str, Any],
    width: int,
    height: int,
) -> Viewport:
    raw = _capability(capabilities, "appium:viewportRect", "viewportRect")
    if not isinstance(raw, Mapping):
        return Viewport(0, 0, width, height)
    try:
        viewport = Viewport(
            x=int(raw.get("left", raw.get("x", 0))),
            y=int(raw.get("top", raw.get("y", 0))),
            width=int(raw.get("width", width)),
            height=int(raw.get("height", height)),
        )
        if viewport.x + viewport.width > width or viewport.y + viewport.height > height:
            return Viewport(0, 0, width, height)
        return viewport
    except (TypeError, ValueError):
        return Viewport(0, 0, width, height)


def _orientation(driver: Any) -> str:
    try:
        orientation = str(driver.orientation).strip().lower()
    except Exception:
        return "unknown"
    return orientation or "unknown"
