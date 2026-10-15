"""Platform-specific device behavior behind one reviewed interface."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
import re
from typing import Any, Mapping, Protocol

from selenium.webdriver.support.ui import WebDriverWait

from ..appium.actions import AppiumActions
from ..appium.models import CapturedState
from .profile import DeviceProfile, MobilePlatform


@dataclass(frozen=True)
class DeviceOperationResult:
    operation: str
    elapsed_seconds: float
    details: Mapping[str, Any]


@dataclass(frozen=True)
class DeviceConnectivity:
    """Observable Android radio state, independent of Appium's bitmask API."""

    wifi_enabled: bool
    mobile_data_enabled: bool
    airplane_mode_enabled: bool

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, bool)
            for value in (
                self.wifi_enabled,
                self.mobile_data_enabled,
                self.airplane_mode_enabled,
            )
        ):
            raise ValueError("Connectivity state values must be booleans")

    @classmethod
    def from_appium_mask(cls, value: int) -> DeviceConnectivity:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("Appium network connection state must be a non-negative integer")
        if value & ~0b111:
            raise ValueError(f"Unsupported Appium network state bits: {value:#b}")
        return cls(
            wifi_enabled=bool(value & 0b010),
            mobile_data_enabled=bool(value & 0b100),
            airplane_mode_enabled=bool(value & 0b001),
        )

    def to_appium_mask(self) -> int:
        return (
            (0b010 if self.wifi_enabled else 0)
            | (0b100 if self.mobile_data_enabled else 0)
            | (0b001 if self.airplane_mode_enabled else 0)
        )


class DeviceOperationError(RuntimeError):
    """A platform operation failed with optional local evidence."""

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


class PlatformDeviceAdapter(Protocol):
    profile: DeviceProfile
    settings_app_id: str

    def go_home(self, *, timeout_seconds: float = 10.0) -> DeviceOperationResult: ...

    def launch_settings_root(
        self,
        *,
        timeout_seconds: float = 10.0,
    ) -> DeviceOperationResult: ...

    def is_app_installed(self, app_id: str) -> bool: ...

    def launch_app(
        self,
        app_id: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> DeviceOperationResult: ...

    def get_connectivity(self) -> DeviceConnectivity: ...

    def set_connectivity(
        self,
        state: DeviceConnectivity,
    ) -> DeviceOperationResult: ...


class AppNotInstalledError(DeviceOperationError):
    """The requested app is not installed on the connected device."""


class AndroidDeviceAdapter:
    settings_app_id = "com.android.settings"

    def __init__(
        self,
        actions: AppiumActions,
        profile: DeviceProfile,
    ) -> None:
        if profile.platform is not MobilePlatform.ANDROID:
            raise ValueError("AndroidDeviceAdapter requires an Android profile")
        self.actions = actions
        self.profile = profile

    def go_home(self, *, timeout_seconds: float = 10.0) -> DeviceOperationResult:
        """Launch Android's default HOME activity and verify its reported component."""
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        started = monotonic()
        try:
            response = self.actions.driver.execute_script(
                "mobile: startActivity",
                {"wait": True, "action": "android.intent.action.MAIN",
                 "categories": ["android.intent.category.HOME"], "flags": "0x10200000"},
            )
            match = re.search(r"Activity:\s*([^\s/]+)/([^\s]+)", str(response))
            if match is None:
                raise RuntimeError("HOME launch did not report its resolved Activity component")
            package, activity = match.groups()
            expected_activity = package + activity if activity.startswith(".") else activity
            def at_home(driver: Any) -> bool:
                current = str(getattr(driver, "current_activity", ""))
                current = package + current if current.startswith(".") else current
                return driver.current_package == package and current == expected_activity
            WebDriverWait(self.actions.driver, timeout_seconds,
                          poll_frequency=self.actions.poll_seconds).until(at_home)
        except Exception as error:
            raise DeviceOperationError("go-home", f"{type(error).__name__}: {error}",
                                       evidence=_capture_failure(self.actions, "go-home")) from error
        return DeviceOperationResult("go-home", monotonic() - started,
                                     {"app_id": package, "activity": expected_activity})

    def launch_settings_root(
        self,
        *,
        timeout_seconds: float = 10.0,
    ) -> DeviceOperationResult:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        started = monotonic()
        try:
            response = self.actions.driver.execute_script(
                "mobile: startActivity",
                {
                    "wait": True,
                    "stop": True,
                    "action": "android.intent.action.MAIN",
                    "component": "com.android.settings/.Settings",
                    "categories": ["android.intent.category.LAUNCHER"],
                    # NEW_TASK | CLEAR_TASK prevents restoration of a stale sub-screen.
                    "flags": "0x10008000",
                },
            )
            WebDriverWait(
                self.actions.driver,
                timeout_seconds,
                poll_frequency=self.actions.poll_seconds,
            ).until(
                lambda driver: getattr(driver, "current_package", None)
                == self.settings_app_id
            )
        except Exception as error:
            evidence = _capture_failure(self.actions, "launch-android-settings")
            raise DeviceOperationError(
                "launch-settings-root",
                f"{type(error).__name__}: {error}",
                evidence=evidence,
            ) from error
        return DeviceOperationResult(
            operation="launch-settings-root",
            elapsed_seconds=monotonic() - started,
            details={
                "platform": self.profile.platform.value,
                "app_id": self.settings_app_id,
                "activity": getattr(self.actions.driver, "current_activity", None),
                "response": response,
            },
        )

    def is_app_installed(self, app_id: str) -> bool:
        app_id = _validate_app_id(app_id)
        try:
            return bool(self.actions.driver.is_app_installed(app_id))
        except Exception as error:
            evidence = _capture_failure(self.actions, "check-app-installed")
            raise DeviceOperationError(
                "check-app-installed",
                f"{type(error).__name__}: {error}",
                evidence=evidence,
            ) from error

    def launch_app(
        self,
        app_id: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> DeviceOperationResult:
        app_id = _validate_app_id(app_id)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        started = monotonic()
        if not self.is_app_installed(app_id):
            raise AppNotInstalledError(
                "launch-app",
                f"application {app_id!r} is not installed",
                evidence=_capture_failure(self.actions, "app-not-installed"),
            )
        try:
            response = self.actions.driver.execute_script(
                "mobile: startActivity",
                {
                    "wait": True,
                    "action": "android.intent.action.MAIN",
                    "package": app_id,
                    "categories": ["android.intent.category.LAUNCHER"],
                    "flags": "0x10200000",
                },
            )
            WebDriverWait(
                self.actions.driver,
                timeout_seconds,
                poll_frequency=self.actions.poll_seconds,
            ).until(lambda driver: _app_is_foreground(driver, app_id))
        except Exception as error:
            evidence = _capture_failure(self.actions, "launch-app")
            raise DeviceOperationError(
                "launch-app",
                f"{type(error).__name__}: {error}",
                evidence=evidence,
            ) from error
        return DeviceOperationResult(
            operation="launch-app",
            elapsed_seconds=monotonic() - started,
            details={
                "platform": self.profile.platform.value,
                "app_id": app_id,
                "current_package": getattr(self.actions.driver, "current_package", None),
                "response": response,
            },
        )

    def get_connectivity(self) -> DeviceConnectivity:
        try:
            return DeviceConnectivity.from_appium_mask(
                self.actions.driver.network_connection
            )
        except Exception as error:
            evidence = _capture_failure(self.actions, "read-connectivity")
            raise DeviceOperationError(
                "read-connectivity",
                f"{type(error).__name__}: {error}",
                evidence=evidence,
            ) from error

    def set_connectivity(
        self,
        state: DeviceConnectivity,
    ) -> DeviceOperationResult:
        if not isinstance(state, DeviceConnectivity):
            raise TypeError("state must be a DeviceConnectivity")
        started = monotonic()
        try:
            self.actions.driver.set_network_connection(state.to_appium_mask())
            actual = self.get_connectivity()
            if actual != state:
                raise RuntimeError(f"requested {state!r}, observed {actual!r}")
        except Exception as error:
            evidence = _capture_failure(self.actions, "set-connectivity")
            raise DeviceOperationError(
                "set-connectivity",
                f"{type(error).__name__}: {error}",
                evidence=evidence,
            ) from error
        return DeviceOperationResult(
            operation="set-connectivity",
            elapsed_seconds=monotonic() - started,
            details={
                "platform": self.profile.platform.value,
                "connectivity": {
                    "wifi_enabled": actual.wifi_enabled,
                    "mobile_data_enabled": actual.mobile_data_enabled,
                    "airplane_mode_enabled": actual.airplane_mode_enabled,
                },
            },
        )


class IOSDeviceAdapter:
    settings_app_id = "com.apple.Preferences"

    def go_home(self, *, timeout_seconds: float = 10.0) -> DeviceOperationResult:
        raise DeviceOperationError("go-home", "verified Home checkpoint is Android-only")

    def __init__(
        self,
        actions: AppiumActions,
        profile: DeviceProfile,
    ) -> None:
        if profile.platform is not MobilePlatform.IOS:
            raise ValueError("IOSDeviceAdapter requires an iOS profile")
        self.actions = actions
        self.profile = profile

    def launch_settings_root(
        self,
        *,
        timeout_seconds: float = 10.0,
    ) -> DeviceOperationResult:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        started = monotonic()
        try:
            self.actions.driver.terminate_app(self.settings_app_id)
            self.actions.driver.activate_app(self.settings_app_id)
            WebDriverWait(
                self.actions.driver,
                timeout_seconds,
                poll_frequency=self.actions.poll_seconds,
            ).until(
                lambda driver: _app_is_foreground(driver, self.settings_app_id)
            )
        except Exception as error:
            evidence = _capture_failure(self.actions, "launch-ios-settings")
            raise DeviceOperationError(
                "launch-settings-root",
                f"{type(error).__name__}: {error}",
                evidence=evidence,
            ) from error
        return DeviceOperationResult(
            operation="launch-settings-root",
            elapsed_seconds=monotonic() - started,
            details={
                "platform": self.profile.platform.value,
                "app_id": self.settings_app_id,
            },
        )

    def is_app_installed(self, app_id: str) -> bool:
        app_id = _validate_app_id(app_id)
        try:
            return bool(self.actions.driver.is_app_installed(app_id))
        except Exception as error:
            evidence = _capture_failure(self.actions, "check-app-installed")
            raise DeviceOperationError(
                "check-app-installed",
                f"{type(error).__name__}: {error}",
                evidence=evidence,
            ) from error

    def launch_app(
        self,
        app_id: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> DeviceOperationResult:
        app_id = _validate_app_id(app_id)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        started = monotonic()
        if not self.is_app_installed(app_id):
            raise AppNotInstalledError(
                "launch-app",
                f"application {app_id!r} is not installed",
                evidence=_capture_failure(self.actions, "app-not-installed"),
            )
        try:
            self.actions.driver.activate_app(app_id)
            WebDriverWait(
                self.actions.driver,
                timeout_seconds,
                poll_frequency=self.actions.poll_seconds,
            ).until(lambda driver: _app_is_foreground(driver, app_id))
        except Exception as error:
            evidence = _capture_failure(self.actions, "launch-app")
            raise DeviceOperationError(
                "launch-app",
                f"{type(error).__name__}: {error}",
                evidence=evidence,
            ) from error
        return DeviceOperationResult(
            operation="launch-app",
            elapsed_seconds=monotonic() - started,
            details={"platform": self.profile.platform.value, "app_id": app_id},
        )

    def get_connectivity(self) -> DeviceConnectivity:
        raise DeviceOperationError(
            "read-connectivity",
            "network radio control is not supported by the iOS adapter",
        )

    def set_connectivity(
        self,
        state: DeviceConnectivity,
    ) -> DeviceOperationResult:
        raise DeviceOperationError(
            "set-connectivity",
            "network radio control is not supported by the iOS adapter",
        )


def create_platform_adapter(
    actions: AppiumActions,
    profile: DeviceProfile,
) -> PlatformDeviceAdapter:
    if profile.platform is MobilePlatform.ANDROID:
        return AndroidDeviceAdapter(actions, profile)
    if profile.platform is MobilePlatform.IOS:
        return IOSDeviceAdapter(actions, profile)
    raise ValueError(f"Unsupported mobile platform: {profile.platform}")


def _app_is_foreground(driver: Any, app_id: str) -> bool:
    state = driver.query_app_state(app_id)
    try:
        return int(state) == 4
    except (TypeError, ValueError):
        return str(state).strip().lower() in {"running_in_foreground", "foreground"}


def _validate_app_id(app_id: str) -> str:
    if not isinstance(app_id, str) or not app_id.strip():
        raise ValueError("app_id must be a non-empty package or bundle identifier")
    normalized = app_id.strip()
    if any(character.isspace() for character in normalized):
        raise ValueError("app_id cannot contain whitespace")
    return normalized


def _capture_failure(
    actions: AppiumActions,
    label: str,
) -> CapturedState | None:
    try:
        return actions.capture_state(label)
    except Exception:
        return None
