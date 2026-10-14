"""Composition root presented to tests and future generated regressions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ..appium.actions import AppiumActions, SwipeDirection
from ..appium.models import ActionResult, OverlayRule
from ..appium.targets import AppiumTargetResolver, ResolvedTarget, TargetCatalog, TargetState
from .platform import (
    DeviceConnectivity,
    DeviceOperationResult,
    PlatformDeviceAdapter,
    create_platform_adapter,
)
from .profile import DeviceGeometry, DeviceProfile


class SystemSettings:
    """Cross-platform entry point for the operating system Settings app."""

    def __init__(self, adapter: PlatformDeviceAdapter) -> None:
        self._adapter = adapter

    def launch_root(self, *, timeout_seconds: float = 10.0) -> DeviceOperationResult:
        return self._adapter.launch_settings_root(timeout_seconds=timeout_seconds)


class DeviceApplications:
    """Installed-app checks and foreground launches shared by mobile tests."""

    def __init__(self, adapter: PlatformDeviceAdapter) -> None:
        self._adapter = adapter

    def is_installed(self, app_id: str) -> bool:
        return self._adapter.is_app_installed(app_id)

    def launch(
        self,
        app_id: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> DeviceOperationResult:
        return self._adapter.launch_app(app_id, timeout_seconds=timeout_seconds)


class DeviceNetwork:
    """Network state controls with explicit capture/restore for test cleanup."""

    def __init__(self, adapter: PlatformDeviceAdapter) -> None:
        self._adapter = adapter

    def get_connectivity(self) -> DeviceConnectivity:
        return self._adapter.get_connectivity()

    def set_connectivity(self, state: DeviceConnectivity) -> DeviceOperationResult:
        return self._adapter.set_connectivity(state)

    def set_airplane_mode(self, enabled: bool) -> DeviceOperationResult:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        current = self.get_connectivity()
        requested = (
            DeviceConnectivity(False, False, True)
            if enabled
            else DeviceConnectivity(
                current.wifi_enabled,
                current.mobile_data_enabled,
                False,
            )
        )
        return self.set_connectivity(requested)


class SemanticUI:
    """Use durable target names while AppiumActions owns physical interaction."""

    def __init__(
        self,
        actions: AppiumActions,
        catalog: TargetCatalog,
        resolver: AppiumTargetResolver,
    ) -> None:
        self.actions = actions
        self.catalog = catalog
        self.resolver = resolver

    def resolve(
        self,
        target_id: str,
        *,
        state: TargetState = "visible",
        timeout_seconds: float | None = None,
    ) -> ResolvedTarget:
        return self.resolver.resolve(
            self.catalog.require(target_id),
            state=state,
            timeout_seconds=timeout_seconds,
        )

    def find(
        self,
        target_id: str,
        *,
        state: TargetState = "visible",
        timeout_seconds: float | None = None,
    ) -> Any:
        resolved = self.resolve(
            target_id,
            state=state,
            timeout_seconds=timeout_seconds,
        )
        return self.actions.find(
            resolved.locator,
            state=state,
            timeout_seconds=timeout_seconds,
        )

    def tap(
        self,
        target_id: str,
        *,
        expected_target_id: str | None = None,
        timeout_seconds: float | None = None,
        overlays: Iterable[OverlayRule] = (),
    ) -> ActionResult:
        resolved = self.resolve(
            target_id,
            state="clickable",
            timeout_seconds=timeout_seconds,
        )
        postcondition = None
        if expected_target_id is not None:
            expected = self.catalog.require(expected_target_id)
            postcondition = lambda: self.resolver.is_available(
                expected,
                state="visible",
            )
        return self.actions.tap(
            resolved.locator,
            overlays=overlays,
            postcondition=postcondition,
            timeout_seconds=timeout_seconds,
        )

    def type_text(
        self,
        target_id: str,
        text: str,
        *,
        clear_first: bool = True,
        timeout_seconds: float | None = None,
        overlays: Iterable[OverlayRule] = (),
    ) -> ActionResult:
        """Type into a reviewed semantic target through the existing action layer."""
        resolved = self.resolve(
            target_id,
            state="clickable",
            timeout_seconds=timeout_seconds,
        )
        return self.actions.type_text(
            resolved.locator,
            text,
            clear_first=clear_first,
            overlays=overlays,
            timeout_seconds=timeout_seconds,
        )

    def scroll_until_visible(
        self,
        target_id: str,
        *,
        direction: SwipeDirection = "up",
        max_swipes: int = 5,
        overlays: Iterable[OverlayRule] = (),
    ) -> ActionResult:
        target = self.catalog.require(target_id)
        result = self.actions.scroll_until_visible(
            target.preferred_locator,
            direction=direction,
            max_swipes=max_swipes,
            overlays=overlays,
        )
        self.resolver.resolve(target, state="visible", timeout_seconds=0)
        return result


class MobileDevice:
    """One cohesive, inspectable facade over identity, platform, and UI adapters."""

    def __init__(
        self,
        *,
        driver: Any,
        profile: DeviceProfile,
        actions: AppiumActions,
        platform: PlatformDeviceAdapter,
        settings: SystemSettings,
        apps: DeviceApplications,
        network: DeviceNetwork,
        ui: SemanticUI,
    ) -> None:
        self.driver = driver
        self.profile = profile
        self.actions = actions
        self.platform = platform
        self.settings = settings
        self.apps = apps
        self.network = network
        self.ui = ui

    @classmethod
    def create(
        cls,
        driver: Any,
        *,
        evidence_dir: Path,
        target_catalog: Path,
        default_timeout_seconds: float = 10.0,
        poll_seconds: float = 0.2,
        record_successful_actions: bool = False,
    ) -> "MobileDevice":
        profile = DeviceProfile.from_driver(driver)
        actions = AppiumActions(
            driver,
            evidence_dir=evidence_dir,
            default_timeout_seconds=default_timeout_seconds,
            poll_seconds=poll_seconds,
            record_successful_actions=record_successful_actions,
        )
        catalog = TargetCatalog.load(target_catalog)
        resolver = AppiumTargetResolver(
            actions,
            trace_path=Path(evidence_dir) / "locator-trace.jsonl",
        )
        platform = create_platform_adapter(actions, profile)
        return cls(
            driver=driver,
            profile=profile,
            actions=actions,
            platform=platform,
            settings=SystemSettings(platform),
            apps=DeviceApplications(platform),
            network=DeviceNetwork(platform),
            ui=SemanticUI(actions, catalog, resolver),
        )

    @property
    def geometry(self) -> DeviceGeometry:
        """Capture current geometry so rotations do not leave stale dimensions."""

        return DeviceGeometry.from_driver(self.driver)
