"""Cross-platform mobile device facade."""

from .facade import (
    DeviceApplications,
    DeviceNetwork,
    MobileDevice,
    SemanticUI,
    SystemSettings,
)
from .platform import (
    AppNotInstalledError,
    AndroidDeviceAdapter,
    DeviceConnectivity,
    DeviceOperationError,
    DeviceOperationResult,
    IOSDeviceAdapter,
    PlatformDeviceAdapter,
    create_platform_adapter,
)
from .profile import DeviceGeometry, DeviceProfile, MobilePlatform, Viewport

__all__ = [
    "AndroidDeviceAdapter",
    "AppNotInstalledError",
    "DeviceApplications",
    "DeviceConnectivity",
    "DeviceGeometry",
    "DeviceNetwork",
    "DeviceOperationError",
    "DeviceOperationResult",
    "DeviceProfile",
    "IOSDeviceAdapter",
    "MobileDevice",
    "MobilePlatform",
    "PlatformDeviceAdapter",
    "SemanticUI",
    "SystemSettings",
    "Viewport",
    "create_platform_adapter",
]
