"""Contract checks for the cross-platform device facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentic_mobile_test.appium.models import CapturedState
from agentic_mobile_test.device import (
    AndroidDeviceAdapter,
    DeviceGeometry,
    DeviceOperationError,
    DeviceProfile,
    IOSDeviceAdapter,
    MobileDevice,
    MobilePlatform,
)

TARGETS_PATH = Path(__file__).with_name("targets") / "android_settings.json"


def test_android_profile_geometry_and_settings_launch(tmp_path: Path) -> None:
    driver = _AndroidDriver()
    profile = DeviceProfile.from_driver(driver)
    actions = _Actions(driver, tmp_path)

    result = AndroidDeviceAdapter(actions, profile).launch_settings_root()
    geometry = DeviceGeometry.from_driver(driver)

    assert profile == DeviceProfile(
        platform=MobilePlatform.ANDROID,
        model="sdk_gphone64_arm64",
        os_version="15",
        identifier="emulator-5554",
    )
    assert result.details["app_id"] == "com.android.settings"
    assert driver.scripts == [
        (
            "mobile: startActivity",
            {
                "wait": True,
                "stop": True,
                "action": "android.intent.action.MAIN",
                "component": "com.android.settings/.Settings",
                "categories": ["android.intent.category.LAUNCHER"],
                "flags": "0x10008000",
            },
        )
    ]
    assert geometry.width == 1080
    assert geometry.height == 2400
    assert geometry.orientation == "portrait"
    assert geometry.pixel_ratio == 2.75
    assert geometry.viewport.y == 72
    assert geometry.viewport.height == 2208


def test_ios_adapter_uses_same_settings_contract(tmp_path: Path) -> None:
    driver = _IOSDriver()
    profile = DeviceProfile.from_driver(driver)

    result = IOSDeviceAdapter(_Actions(driver, tmp_path), profile).launch_settings_root()

    assert profile.platform is MobilePlatform.IOS
    assert profile.model == "iPhone 16"
    assert driver.terminated == ["com.apple.Preferences"]
    assert driver.activated == ["com.apple.Preferences"]
    assert result.details == {
        "platform": "ios",
        "app_id": "com.apple.Preferences",
    }


def test_platform_failure_is_typed_and_captures_evidence(tmp_path: Path) -> None:
    driver = _AndroidDriver(fail_launch=True)
    actions = _Actions(driver, tmp_path)

    with pytest.raises(DeviceOperationError, match="launch-settings-root") as captured:
        AndroidDeviceAdapter(
            actions,
            DeviceProfile.from_driver(driver),
        ).launch_settings_root()

    assert captured.value.operation == "launch-settings-root"
    assert captured.value.evidence is not None
    assert actions.capture_labels == ["launch-android-settings"]


def test_mobile_device_composes_services_and_refreshes_geometry(tmp_path: Path) -> None:
    driver = _AndroidDriver()
    device = MobileDevice.create(
        driver,
        evidence_dir=tmp_path / "evidence",
        target_catalog=TARGETS_PATH,
    )

    before = device.geometry
    driver.window_size = {"width": 2400, "height": 1080}
    driver.orientation = "LANDSCAPE"
    after = device.geometry

    assert device.actions.driver is driver
    assert device.profile.platform is MobilePlatform.ANDROID
    assert (before.width, before.height) == (1080, 2400)
    assert (after.width, after.height) == (2400, 1080)
    assert after.orientation == "landscape"
    assert after.viewport.width == 2400
    assert after.viewport.height == 1080


class _Actions:
    default_timeout_seconds = 0.1
    poll_seconds = 0.01

    def __init__(self, driver: Any, evidence_dir: Path) -> None:
        self.driver = driver
        self.evidence_dir = evidence_dir
        self.capture_labels: list[str] = []

    def capture_state(self, label: str) -> CapturedState:
        self.capture_labels.append(label)
        screenshot = self.evidence_dir / f"{label}.png"
        ui_source = self.evidence_dir / f"{label}.xml"
        screenshot.write_bytes(b"image")
        ui_source.write_text("<hierarchy />", encoding="utf-8")
        return CapturedState(screenshot=screenshot, ui_source=ui_source)


class _AndroidDriver:
    current_package = "com.example"
    current_activity = ".MainActivity"
    orientation = "PORTRAIT"

    def __init__(self, *, fail_launch: bool = False) -> None:
        self.fail_launch = fail_launch
        self.scripts: list[tuple[str, dict[str, Any]]] = []
        self.window_size = {"width": 1080, "height": 2400}
        self.capabilities = {
            "platformName": "Android",
            "appium:deviceModel": "sdk_gphone64_arm64",
            "appium:platformVersion": "15",
            "appium:udid": "emulator-5554",
            "appium:pixelRatio": 2.75,
            "appium:viewportRect": {
                "left": 0,
                "top": 72,
                "width": 1080,
                "height": 2208,
            },
        }

    def execute_script(self, script: str, arguments: dict[str, Any]) -> None:
        if self.fail_launch:
            raise RuntimeError("device command rejected")
        self.scripts.append((script, arguments))
        self.current_package = "com.android.settings"
        self.current_activity = ".Settings"

    def get_window_size(self) -> dict[str, int]:
        return self.window_size


class _IOSDriver:
    orientation = "PORTRAIT"

    def __init__(self) -> None:
        self.capabilities = {
            "platformName": "iOS",
            "appium:deviceName": "iPhone 16",
            "appium:platformVersion": "18.2",
            "appium:udid": "ios-simulator-id",
        }
        self.terminated: list[str] = []
        self.activated: list[str] = []

    def terminate_app(self, app_id: str) -> None:
        self.terminated.append(app_id)

    def activate_app(self, app_id: str) -> None:
        self.activated.append(app_id)

    def query_app_state(self, app_id: str) -> int:
        return 4 if app_id in self.activated else 1
