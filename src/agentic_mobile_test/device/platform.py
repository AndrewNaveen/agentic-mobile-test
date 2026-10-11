"""Platform-specific device behavior behind one reviewed interface."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
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

    def launch_settings_root(
        self,
        *,
        timeout_seconds: float = 10.0,
    ) -> DeviceOperationResult: ...


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


class IOSDeviceAdapter:
    settings_app_id = "com.apple.Preferences"

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


def _capture_failure(
    actions: AppiumActions,
    label: str,
) -> CapturedState | None:
    try:
        return actions.capture_state(label)
    except Exception:
        return None
