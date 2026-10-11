"""Shared pytest configuration for Android Appium tests."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

import pytest

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPIUM_URL = "http://127.0.0.1:4723"
DEFAULT_ANDROID_HOME = Path.home() / "Library/Android/sdk"
DEFAULT_JAVA_HOME = Path("/Applications/Android Studio.app/Contents/jbr/Contents/Home")


@dataclass(frozen=True)
class AppiumTestConfig:
    server_url: str
    udid: str
    app_path: Path | None
    app_package: str | None
    app_activity: str | None
    platform_version: str | None
    no_reset: bool
    auto_grant_permissions: bool


def pytest_addoption(parser: Any) -> None:
    model_group = parser.getgroup("model", "Paid model experiment options")
    model_group.addoption(
        "--run-gemini",
        action="store_true",
        default=False,
        help="Enable tests that make paid Gemini API requests",
    )

    group = parser.getgroup("appium", "Appium Android test options")
    group.addoption(
        "--appium-server-url",
        dest="appium_server_url",
        default=os.getenv("APPIUM_SERVER_URL", DEFAULT_APPIUM_URL),
        help=f"Appium server URL (default: {DEFAULT_APPIUM_URL})",
    )
    group.addoption(
        "--appium-udid",
        dest="appium_udid",
        default=os.getenv("APPIUM_UDID"),
        help="Android device serial from 'adb devices'",
    )
    group.addoption(
        "--appium-app",
        dest="appium_app",
        default=os.getenv("APPIUM_APP"),
        help="Path to the APK under test",
    )
    group.addoption(
        "--appium-package",
        dest="appium_package",
        default=os.getenv("APPIUM_APP_PACKAGE"),
        help="Installed Android application package",
    )
    group.addoption(
        "--appium-activity",
        dest="appium_activity",
        default=os.getenv("APPIUM_APP_ACTIVITY"),
        help="Android launch activity used with --appium-package",
    )
    group.addoption(
        "--appium-platform-version",
        dest="appium_platform_version",
        default=os.getenv("APPIUM_PLATFORM_VERSION"),
        help="Expected Android platform version",
    )
    group.addoption(
        "--appium-no-reset",
        dest="appium_no_reset",
        action="store_true",
        default=_env_flag("APPIUM_NO_RESET"),
        help="Preserve application data between Appium sessions",
    )
    group.addoption(
        "--appium-auto-grant-permissions",
        dest="appium_auto_grant_permissions",
        action="store_true",
        default=_env_flag("APPIUM_AUTO_GRANT_PERMISSIONS"),
        help="Grant declared Android permissions when the application is installed",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if config.getoption("run_gemini"):
        return
    skip = pytest.mark.skip(reason="Pass --run-gemini to permit a paid Gemini request")
    for item in items:
        if "gemini" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def appium_config(pytestconfig: pytest.Config) -> AppiumTestConfig:
    udid = pytestconfig.getoption("appium_udid")
    if not udid:
        pytest.skip("Set --appium-udid or APPIUM_UDID to run Appium tests")

    raw_app_path = pytestconfig.getoption("appium_app")
    app_package = pytestconfig.getoption("appium_package")
    app_activity = pytestconfig.getoption("appium_activity")
    if not raw_app_path and not app_package:
        pytest.skip(
            "Set --appium-app or --appium-package to identify the Android application"
        )
    if app_activity and not app_package:
        pytest.fail("--appium-activity requires --appium-package", pytrace=False)
    if app_package and not raw_app_path and not app_activity:
        pytest.fail(
            "An installed application requires both --appium-package and "
            "--appium-activity",
            pytrace=False,
        )

    app_path = Path(raw_app_path).expanduser().resolve() if raw_app_path else None
    if app_path is not None and not app_path.is_file():
        pytest.fail(f"Appium APK does not exist: {app_path}", pytrace=False)

    server_url = str(pytestconfig.getoption("appium_server_url")).rstrip("/")
    _server_address(server_url)
    return AppiumTestConfig(
        server_url=server_url,
        udid=str(udid),
        app_path=app_path,
        app_package=app_package,
        app_activity=app_activity,
        platform_version=pytestconfig.getoption("appium_platform_version"),
        no_reset=bool(pytestconfig.getoption("appium_no_reset")),
        auto_grant_permissions=bool(
            pytestconfig.getoption("appium_auto_grant_permissions")
        ),
    )


@pytest.fixture(scope="session")
def appium_server(appium_config: AppiumTestConfig) -> Iterator[str]:
    """Use an existing Appium server or own a project-local server for this run."""

    if _appium_is_ready(appium_config.server_url):
        LOGGER.info("Using existing Appium server at %s", appium_config.server_url)
        yield appium_config.server_url
        return

    from appium.webdriver.appium_service import AppiumService, AppiumServiceError

    host, port = _server_address(appium_config.server_url)
    if host not in {"127.0.0.1", "localhost"}:
        pytest.fail(
            f"Remote Appium server is not ready: {appium_config.server_url}",
            pytrace=False,
        )
    appium_main = PROJECT_ROOT / "node_modules/appium/build/lib/main.js"
    if not appium_main.is_file():
        pytest.fail("Project Appium is missing. Run 'npm ci' first.", pytrace=False)
    uiautomator2 = PROJECT_ROOT / ".appium-home/node_modules/appium-uiautomator2-driver"
    if not uiautomator2.is_dir():
        pytest.fail(
            "Project UiAutomator2 driver is missing. Run 'npm run appium:setup' first.",
            pytrace=False,
        )

    environment = _appium_environment()
    node = shutil.which("node", path=environment["PATH"])
    if node is None:
        pytest.fail("Node.js is unavailable. Install the project prerequisites.", pytrace=False)

    log_dir = PROJECT_ROOT / "runs/appium-server"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    log_path = log_dir / f"{timestamp}.log"
    service = AppiumService()

    with log_path.open("wb") as server_log:
        try:
            service.start(
                node=node,
                main_script=str(appium_main),
                env=environment,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                timeout_ms=60_000,
                args=[
                    "--address",
                    host,
                    "--port",
                    str(port),
                    "--session-override",
                ],
            )
        except AppiumServiceError as error:
            pytest.fail(
                f"Unable to start Appium. Log: {log_path}\n{_tail(log_path)}\n{error}",
                pytrace=False,
            )

        if not service.is_running or not service.is_listening:
            service.stop()
            pytest.fail(
                f"Appium started but is not listening. Log: {log_path}\n{_tail(log_path)}",
                pytrace=False,
            )

        LOGGER.info("Started Appium at %s; log: %s", appium_config.server_url, log_path)
        try:
            yield appium_config.server_url
        finally:
            LOGGER.info("Stopping pytest-owned Appium server")
            service.stop()
            if service.is_running or service.is_listening:
                pytest.fail("The pytest-owned Appium server did not stop", pytrace=False)


@pytest.fixture
def appium_options(appium_config: AppiumTestConfig) -> tuple[Any, dict[str, Any]]:
    from appium.options.android import UiAutomator2Options

    capabilities: dict[str, Any] = {
        "platformName": "Android",
        "appium:automationName": "UiAutomator2",
        "appium:udid": appium_config.udid,
        "appium:newCommandTimeout": 120,
        "appium:noReset": appium_config.no_reset,
        "appium:autoGrantPermissions": appium_config.auto_grant_permissions,
    }
    if appium_config.app_path is not None:
        capabilities["appium:app"] = str(appium_config.app_path)
    if appium_config.app_package:
        capabilities["appium:appPackage"] = appium_config.app_package
    if appium_config.app_activity:
        capabilities["appium:appActivity"] = appium_config.app_activity
        capabilities["appium:forceAppLaunch"] = True
    if appium_config.platform_version:
        capabilities["appium:platformVersion"] = appium_config.platform_version

    options = UiAutomator2Options().load_capabilities(capabilities)
    return options, capabilities


@pytest.fixture
def driver(
    appium_server: str,
    appium_options: tuple[Any, dict[str, Any]],
) -> Iterator[Any]:
    """Create one isolated Appium session for each test that requests it."""

    from appium import webdriver
    from selenium.common.exceptions import WebDriverException

    options, capabilities = appium_options
    LOGGER.info("Starting Appium session with capabilities: %s", capabilities)
    try:
        mobile_driver = webdriver.Remote(
            command_executor=appium_server,
            options=options,
        )
    except WebDriverException as error:
        pytest.fail(f"Unable to start Appium WebDriver: {error.msg}", pytrace=False)

    try:
        yield mobile_driver
    finally:
        LOGGER.info("Stopping Appium session %s", mobile_driver.session_id)
        mobile_driver.quit()


@pytest.fixture
def runs_directory() -> Path:
    return Path("runs")


def _env_flag(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    if value in {"", "0", "false", "no"}:
        return False
    if value in {"1", "true", "yes"}:
        return True
    raise pytest.UsageError(f"{name} must be true/false, yes/no, or 1/0")


def _server_address(server_url: str) -> tuple[str, int]:
    parsed = urlparse(server_url)
    if parsed.scheme != "http" or parsed.hostname is None or parsed.path not in {"", "/"}:
        raise pytest.UsageError(
            "Appium server URL must use HTTP and contain only a host and optional port"
        )
    return parsed.hostname, parsed.port or 4723


def _appium_is_ready(server_url: str) -> bool:
    try:
        with urlopen(f"{server_url}/status", timeout=0.5) as response:
            body = json.loads(response.read())
        return response.status == 200 and body.get("value", {}).get("ready") is True
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _appium_environment() -> dict[str, str]:
    environment = os.environ.copy()
    android_home = Path(environment.get("ANDROID_HOME", DEFAULT_ANDROID_HOME)).expanduser()
    java_home = Path(environment.get("JAVA_HOME", DEFAULT_JAVA_HOME)).expanduser()
    adb = android_home / "platform-tools/adb"
    java = java_home / "bin/java"
    if not adb.is_file():
        pytest.fail(f"Android platform-tools are missing under {android_home}", pytrace=False)
    if not java.is_file():
        pytest.fail(f"Java is missing under {java_home}", pytrace=False)

    environment["APPIUM_HOME"] = str(PROJECT_ROOT / ".appium-home")
    environment["ANDROID_HOME"] = str(android_home)
    environment["ANDROID_SDK_ROOT"] = environment.get("ANDROID_SDK_ROOT", str(android_home))
    environment["JAVA_HOME"] = str(java_home)
    environment["PATH"] = os.pathsep.join(
        [
            str(android_home / "platform-tools"),
            str(android_home / "emulator"),
            str(java_home / "bin"),
            environment.get("PATH", ""),
        ]
    )
    return environment


def _tail(path: Path, line_count: int = 40) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-line_count:])
    except OSError:
        return "Appium log could not be read"
