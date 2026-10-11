"""Cross-platform mobile device facade."""

from .facade import MobileDevice, SemanticUI, SystemSettings
from .platform import (
    AndroidDeviceAdapter,
    DeviceOperationError,
    DeviceOperationResult,
    IOSDeviceAdapter,
    PlatformDeviceAdapter,
    create_platform_adapter,
)
from .profile import DeviceGeometry, DeviceProfile, MobilePlatform, Viewport

__all__ = [
    "AndroidDeviceAdapter",
    "DeviceGeometry",
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
