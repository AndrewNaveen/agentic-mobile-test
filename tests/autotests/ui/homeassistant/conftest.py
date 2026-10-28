"""Fixtures for the isolated Home Assistant demo app."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from appium.webdriver.common.appiumby import AppiumBy

from agentic_mobile_test.appium import AppiumActions, Locator


_OVERVIEW = (AppiumBy.XPATH, "//*[@text='Overview']")
_PLAYING_CARD = (
    AppiumBy.XPATH,
    "//*[@text='Living RoomPlaying']/ancestor::*"
    "[android.widget.Button[@clickable='true']][1]"
    "/android.widget.Button[@clickable='true']",
)
_DIALOG = (
    "//*[@class='android.widget.TextView' and @text='Living Room']"
    "/ancestor::*[.//*[@content-desc='Close'] and "
    ".//*[@class='android.widget.Button' and (@text='Play' or @text='Pause')]][1]"
)
_CLOSE = (
    AppiumBy.XPATH,
    _DIALOG + "//*[@class='android.widget.Button' and @content-desc='Close']",
)


@dataclass
class LivingRoomPlayer:
    """App-local controls; labels describe UI state, not physical playback."""

    driver: Any
    actions: AppiumActions

    def visible(self, locator: Locator) -> bool:
        matches = self.driver.find_elements(*locator)
        return len(matches) == 1 and matches[0].is_displayed()

    def control(self, label: str) -> Locator:
        if label not in {"Play", "Pause"}:
            raise ValueError(f"Unsupported playback control: {label}")
        return (
            AppiumBy.XPATH,
            _DIALOG + f"//*[@class='android.widget.Button' and @text='{label}']",
        )

    def shows_control(self, label: str) -> bool:
        return self.visible(self.control(label))

    def pause(self) -> None:
        self.actions.tap(
            self.control("Pause"),
            postcondition=lambda: self.shows_control("Play")
            and not self.shows_control("Pause"),
        )

    def restore_overview_playing(self) -> None:
        if self.visible(_OVERVIEW) and self.visible(_PLAYING_CARD):
            self.actions.capture_state("restored-overview-playing")
            return
        if not self.visible(_CLOSE):
            raise RuntimeError("Cannot restore: the Living Room player dialog is not identifiable")
        if self.shows_control("Play"):
            self.actions.tap(
                self.control("Play"),
                postcondition=lambda: self.shows_control("Pause")
                and not self.shows_control("Play"),
            )
        elif not self.shows_control("Pause"):
            raise RuntimeError("Cannot restore: playback control state is unknown")
        self.actions.tap(
            _CLOSE,
            postcondition=lambda: self.visible(_OVERVIEW)
            and self.visible(_PLAYING_CARD)
            and not self.visible(_CLOSE),
        )
        self.actions.capture_state("restored-overview-playing")


@pytest.fixture
def playing_living_room(request, appium_config, capsys) -> Iterator[LivingRoomPlayer]:
    """Require an already-playing demo player; never toggle playback in setup."""
    if appium_config.app_package != "io.homeassistant.companion.android":
        pytest.fail("Use the full Home Assistant demo app package for this test", pytrace=False)
    if not appium_config.no_reset:
        pytest.fail("Pass --appium-no-reset to preserve the prepared demo login", pytrace=False)

    driver = request.getfixturevalue("driver")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    evidence_dir = (
        Path(__file__).resolve().parents[4]
        / "runs/apps/home-assistant/pause-control"
        / f"replay-{timestamp}-{uuid4().hex[:8]}"
    )
    actions = AppiumActions(
        driver, evidence_dir=evidence_dir, record_successful_actions=True,
    )
    player = LivingRoomPlayer(driver, actions)
    with capsys.disabled():
        print(f"\nReplay evidence: {evidence_dir}")
    actions.capture_state("initial-state")
    if driver.current_package != appium_config.app_package:
        pytest.fail("The prepared Home Assistant app is not foregrounded", pytrace=False)
    if not actions.wait_until_visible(_PLAYING_CARD):
        actions.capture_state("playing-precondition-failed")
        pytest.fail(
            "Precondition: open Overview with the isolated Living Room demo player playing; "
            "setup will not toggle playback to prepare it",
            pytrace=False,
        )

    try:
        actions.tap(_PLAYING_CARD, postcondition=lambda: player.shows_control("Pause"))
        yield player
    finally:
        # Retain the test's final state even when an assertion fails, then restore.
        try:
            actions.capture_state("before-cleanup")
        finally:
            player.restore_overview_playing()
