"""Deterministic, evidence-aware actions on top of an Appium WebDriver."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any, Literal

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.support import expected_conditions as expected
from selenium.webdriver.support.ui import WebDriverWait

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

ElementState = Literal["present", "visible", "enabled", "clickable"]
SwipeDirection = Literal["up", "down", "left", "right"]
_SAFE_LABEL = re.compile(r"[^a-zA-Z0-9_.-]+")
_PERCENT_VALUE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:%|percent\b)", re.IGNORECASE)
_PLAIN_NUMBER = re.compile(r"\s*(-?\d+(?:\.\d+)?)\s*")


def _element_to_be_enabled(locator: Locator) -> Callable[[Any], Any]:
    def predicate(driver: Any) -> Any:
        element = driver.find_element(*locator)
        return element if element.is_enabled() else False

    return predicate


class AppiumActions:
    """Reusable touchscreen operations with bounded waits and visible failures.

    Tests provide locators and expected outcomes. This class owns only the
    deterministic mechanics: waiting, tapping, typing, swiping, scrolling,
    known-overlay handling, slider movement, and state capture.
    """

    def __init__(
        self,
        driver: Any,
        *,
        evidence_dir: Path,
        default_timeout_seconds: float = 10.0,
        poll_seconds: float = 0.2,
        record_successful_actions: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        if default_timeout_seconds <= 0:
            raise ValueError("default_timeout_seconds must be greater than zero")
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be greater than zero")

        self.driver = driver
        self.evidence_dir = Path(evidence_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.default_timeout_seconds = default_timeout_seconds
        self.poll_seconds = poll_seconds
        self.record_successful_actions = record_successful_actions
        self.logger = logger or logging.getLogger(__name__)
        self._capture_number = 0

    def find(
        self,
        locator: Locator,
        *,
        state: ElementState = "visible",
        timeout_seconds: float | None = None,
    ) -> Any:
        """Wait for one element in the requested state and return it."""

        conditions = {
            "present": expected.presence_of_element_located,
            "visible": expected.visibility_of_element_located,
            "enabled": _element_to_be_enabled,
            "clickable": expected.element_to_be_clickable,
        }
        if state not in conditions:
            raise ValueError(f"Unsupported element state: {state}")
        return self._wait(timeout_seconds).until(conditions[state](locator))

    def wait_until(
        self,
        locator: Locator,
        *,
        state: ElementState = "visible",
        timeout_seconds: float | None = None,
    ) -> bool:
        """Return whether a locator reaches a UI state within a bounded timeout.

        This mirrors the useful ``BasePage.wait_until_*`` contract while keeping
        polling and timeout behavior in the shared Appium action layer.
        """

        try:
            self.find(locator, state=state, timeout_seconds=timeout_seconds)
        except TimeoutException:
            return False
        return True

    def wait_until_present(
        self,
        locator: Locator,
        *,
        timeout_seconds: float | None = None,
    ) -> bool:
        return self.wait_until(locator, state="present", timeout_seconds=timeout_seconds)

    def wait_until_visible(
        self,
        locator: Locator,
        *,
        timeout_seconds: float | None = None,
    ) -> bool:
        return self.wait_until(locator, state="visible", timeout_seconds=timeout_seconds)

    def wait_until_clickable(
        self,
        locator: Locator,
        *,
        timeout_seconds: float | None = None,
    ) -> bool:
        return self.wait_until(locator, state="clickable", timeout_seconds=timeout_seconds)

    def wait_until_enabled(
        self,
        locator: Locator,
        *,
        timeout_seconds: float | None = None,
    ) -> bool:
        return self.wait_until(locator, state="enabled", timeout_seconds=timeout_seconds)

    def wait_until_gone(
        self,
        locator: Locator,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self._wait(timeout_seconds).until(expected.invisibility_of_element_located(locator))

    def capture_state(self, label: str) -> CapturedState:
        """Write a screenshot and Appium UI source with the same filename stem."""

        self._capture_number += 1
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        safe_label = _SAFE_LABEL.sub("-", label).strip("-") or "state"
        stem = f"{self._capture_number:04d}-{timestamp}-{safe_label}"
        screenshot = (self.evidence_dir / f"{stem}.png").resolve()
        ui_source = (self.evidence_dir / f"{stem}.xml").resolve()

        saved = self.driver.save_screenshot(str(screenshot))
        if saved is False:
            raise RuntimeError(f"Appium did not save screenshot {screenshot}")
        ui_source.write_text(str(self.driver.page_source), encoding="utf-8")
        return CapturedState(screenshot=screenshot, ui_source=ui_source)

    def tap(
        self,
        locator: Locator,
        *,
        overlays: Iterable[OverlayRule] = (),
        postcondition: Callable[[], bool] | None = None,
        timeout_seconds: float | None = None,
    ) -> ActionResult:
        def operation() -> dict[str, Any]:
            dismissed = self._dismiss_known_overlays(overlays)
            element = self.find(locator, state="clickable", timeout_seconds=timeout_seconds)
            element.click()
            self._wait_for_postcondition(postcondition, timeout_seconds)
            return {"locator": locator, "dismissed_overlays": dismissed}

        return self._run("tap", operation)

    def tap_relative(
        self,
        locator: Locator,
        *,
        x_percent: float = 50,
        y_percent: float = 50,
        overlays: Iterable[OverlayRule] = (),
        postcondition: Callable[[], bool] | None = None,
        timeout_seconds: float | None = None,
    ) -> ActionResult:
        def operation() -> dict[str, Any]:
            dismissed = self._dismiss_known_overlays(overlays)
            element = self.find(locator, state="visible", timeout_seconds=timeout_seconds)
            point = Rect.from_element(element).point_at(x_percent, y_percent)
            self._tap_point(point)
            self._wait_for_postcondition(postcondition, timeout_seconds)
            return {
                "locator": locator,
                "point": {"x": point.x, "y": point.y},
                "dismissed_overlays": dismissed,
            }

        return self._run("tap-relative", operation)

    def tap_coordinates(
        self,
        point: Point,
        *,
        postcondition: Callable[[], bool] | None = None,
        timeout_seconds: float | None = None,
    ) -> ActionResult:
        def operation() -> dict[str, Any]:
            self._assert_point_on_screen(point)
            self._tap_point(point)
            self._wait_for_postcondition(postcondition, timeout_seconds)
            return {"point": {"x": point.x, "y": point.y}}

        return self._run("tap-coordinates", operation)

    def type_text(
        self,
        locator: Locator,
        text: str,
        *,
        clear_first: bool = True,
        overlays: Iterable[OverlayRule] = (),
        postcondition: Callable[[], bool] | None = None,
        timeout_seconds: float | None = None,
    ) -> ActionResult:
        def operation() -> dict[str, Any]:
            dismissed = self._dismiss_known_overlays(overlays)
            element = self.find(locator, state="clickable", timeout_seconds=timeout_seconds)
            element.click()
            if clear_first:
                element.clear()
            element.send_keys(text)
            self._wait_for_postcondition(postcondition, timeout_seconds)
            return {
                "locator": locator,
                "character_count": len(text),
                "cleared_first": clear_first,
                "dismissed_overlays": dismissed,
            }

        return self._run("type-text", operation)

    def long_press(
        self,
        locator: Locator,
        *,
        duration_seconds: float = 1.0,
        overlays: Iterable[OverlayRule] = (),
        postcondition: Callable[[], bool] | None = None,
        timeout_seconds: float | None = None,
    ) -> ActionResult:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be greater than zero")

        def operation() -> dict[str, Any]:
            dismissed = self._dismiss_known_overlays(overlays)
            element = self.find(locator, state="visible", timeout_seconds=timeout_seconds)
            point = Rect.from_element(element).point_at(50, 50)
            self._touch(point, point, hold_seconds=duration_seconds, move_duration_seconds=0)
            self._wait_for_postcondition(postcondition, timeout_seconds)
            return {
                "locator": locator,
                "duration_seconds": duration_seconds,
                "dismissed_overlays": dismissed,
            }

        return self._run("long-press", operation)

    def swipe(
        self,
        start: Point,
        end: Point,
        *,
        duration_seconds: float = 0.5,
        postcondition: Callable[[], bool] | None = None,
        timeout_seconds: float | None = None,
    ) -> ActionResult:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be greater than zero")

        def operation() -> dict[str, Any]:
            self._assert_point_on_screen(start)
            self._assert_point_on_screen(end)
            self._touch(start, end, hold_seconds=0.05, move_duration_seconds=duration_seconds)
            self._wait_for_postcondition(postcondition, timeout_seconds)
            return {
                "start": {"x": start.x, "y": start.y},
                "end": {"x": end.x, "y": end.y},
                "duration_seconds": duration_seconds,
            }

        return self._run("swipe", operation)

    def swipe_relative(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        *,
        duration_seconds: float = 0.5,
        postcondition: Callable[[], bool] | None = None,
        timeout_seconds: float | None = None,
    ) -> ActionResult:
        """Swipe using screen fractions, where every value is from 0.0 to 1.0."""

        start_point = self._screen_fraction_to_point(start)
        end_point = self._screen_fraction_to_point(end)
        return self.swipe(
            start_point,
            end_point,
            duration_seconds=duration_seconds,
            postcondition=postcondition,
            timeout_seconds=timeout_seconds,
        )

    def scroll_until_visible(
        self,
        locator: Locator,
        *,
        direction: SwipeDirection = "up",
        max_swipes: int = 5,
        overlays: Iterable[OverlayRule] = (),
    ) -> ActionResult:
        if max_swipes < 0:
            raise ValueError("max_swipes cannot be negative")

        def operation() -> dict[str, Any]:
            dismissed = self._dismiss_known_overlays(overlays)
            for swipe_count in range(max_swipes + 1):
                if self._first_visible(locator) is not None:
                    return {
                        "locator": locator,
                        "direction": direction,
                        "swipes": swipe_count,
                        "dismissed_overlays": dismissed,
                    }
                if swipe_count < max_swipes:
                    start, end = self._scroll_points(direction)
                    self._touch(start, end, hold_seconds=0.05, move_duration_seconds=0.5)
                    try:
                        WebDriverWait(
                            self.driver,
                            0.5,
                            poll_frequency=self.poll_seconds,
                        ).until(lambda _: self._first_visible(locator) is not None)
                    except TimeoutException:
                        pass
            raise NoSuchElementException(
                f"{locator!r} was not visible after {max_swipes} {direction} swipes"
            )

        return self._run("scroll-until-visible", operation)

    def dismiss_if_present(
        self,
        overlay: Locator,
        *,
        dismiss: Locator | None = None,
        timeout_seconds: float = 2.0,
    ) -> ActionResult:
        def operation() -> dict[str, Any]:
            dismissed = self._dismiss_known_overlays(
                (OverlayRule(overlay, dismiss, timeout_seconds),)
            )
            return {"overlay": overlay, "dismissed": bool(dismissed)}

        return self._run("dismiss-if-present", operation)

    def press_back(
        self,
        *,
        postcondition: Callable[[], bool] | None = None,
        timeout_seconds: float | None = None,
    ) -> ActionResult:
        def operation() -> dict[str, Any]:
            self.driver.back()
            self._wait_for_postcondition(postcondition, timeout_seconds)
            return {}

        return self._run("press-back", operation)

    def read_slider_percent(self, element: Any) -> float:
        """Read a 0-100 slider value from common Android and iOS attributes."""

        candidates: list[tuple[str, Any]] = []
        for attribute in ("value", "content-desc"):
            candidates.append((attribute, element.get_attribute(attribute)))
        candidates.append(("text", element.text))
        for attribute in ("label", "name"):
            candidates.append((attribute, element.get_attribute(attribute)))

        for attribute, raw_value in candidates:
            if raw_value is None:
                continue
            value = str(raw_value).strip()
            percent_match = _PERCENT_VALUE.search(value)
            if percent_match:
                parsed = float(percent_match.group(1))
            else:
                number_match = _PLAIN_NUMBER.fullmatch(value)
                if not number_match:
                    continue
                parsed = float(number_match.group(1))
                if attribute == "value" and 0 < parsed < 1:
                    parsed *= 100
            if 0 <= parsed <= 100:
                return parsed

        raise SliderValueUnavailableError(
            "No slider value was found in text, value, content-desc, label, or name"
        )

    def set_slider_value(
        self,
        locator: Locator,
        target_percent: float,
        *,
        current_percent: float | None = None,
        value_reader: Callable[[Any], float] | None = None,
        independent_reader: Callable[[], float] | None = None,
        tolerance_percent: float = 2.0,
        max_attempts: int = 3,
        track_inset_percent: float = 2.0,
        drag_duration_seconds: float = 0.5,
        verification_timeout_seconds: float = 2.0,
        overlays: Iterable[OverlayRule] = (),
    ) -> SliderResult:
        """Move a slider to an absolute value and verify it with bounded retries.

        ``value_reader`` reads the slider's UI value. ``independent_reader`` can
        read the real product state through another test interface. If the UI
        exposes no numeric value, provide both ``current_percent`` and an
        ``independent_reader``.
        """

        if not 0 <= target_percent <= 100:
            raise ValueError("target_percent must be between 0 and 100")
        if current_percent is not None and not 0 <= current_percent <= 100:
            raise ValueError("current_percent must be between 0 and 100")
        if tolerance_percent < 0:
            raise ValueError("tolerance_percent cannot be negative")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if not 0 <= track_inset_percent < 50:
            raise ValueError("track_inset_percent must be from 0 up to 50")
        if drag_duration_seconds <= 0 or verification_timeout_seconds <= 0:
            raise ValueError("Gesture and verification timeouts must be greater than zero")

        reader = value_reader or self.read_slider_percent
        outcome: dict[str, Any] = {}

        def operation() -> dict[str, Any]:
            dismissed = self._dismiss_known_overlays(overlays)
            self.find(locator, state="visible")
            ui_value = self._try_slider_read(locator, reader)
            working_value = ui_value if ui_value is not None else current_percent
            independent_value = self._read_independent(independent_reader)

            if working_value is None:
                raise SliderValueUnavailableError(
                    "The current slider value is unavailable; provide current_percent "
                    "or a value_reader"
                )
            if ui_value is None and independent_reader is None:
                raise SliderValueUnavailableError(
                    "The slider cannot be verified; provide a value_reader or independent_reader"
                )

            attempts = 0
            if self._slider_values_match(
                target_percent,
                tolerance_percent,
                ui_value,
                independent_value,
            ):
                outcome.update(ui=ui_value, independent=independent_value, attempts=attempts)
                return {
                    "locator": locator,
                    "target_percent": target_percent,
                    "attempts": attempts,
                    "dismissed_overlays": dismissed,
                }

            if self._is_within_tolerance(ui_value, target_percent, tolerance_percent):
                ui_value, independent_value = self._wait_for_slider_values(
                    locator,
                    reader,
                    independent_reader,
                    target_percent,
                    tolerance_percent,
                    verification_timeout_seconds,
                )
                if self._slider_values_match(
                    target_percent,
                    tolerance_percent,
                    ui_value,
                    independent_value,
                ):
                    outcome.update(ui=ui_value, independent=independent_value, attempts=0)
                    return {
                        "locator": locator,
                        "target_percent": target_percent,
                        "attempts": 0,
                        "dismissed_overlays": dismissed,
                    }
                raise AssertionError(
                    f"Slider UI reports {ui_value!r}% but the independent source "
                    f"reports {independent_value!r}%; expected {target_percent}%"
                )

            for attempts in range(1, max_attempts + 1):
                element = self.find(locator, state="visible")
                start, end = self._slider_points(
                    Rect.from_element(element),
                    working_value,
                    target_percent,
                    track_inset_percent,
                )
                self._touch(
                    start,
                    end,
                    hold_seconds=0.05,
                    move_duration_seconds=drag_duration_seconds,
                )

                ui_value, independent_value = self._wait_for_slider_values(
                    locator,
                    reader,
                    independent_reader,
                    target_percent,
                    tolerance_percent,
                    verification_timeout_seconds,
                )
                if self._slider_values_match(
                    target_percent,
                    tolerance_percent,
                    ui_value,
                    independent_value,
                ):
                    outcome.update(ui=ui_value, independent=independent_value, attempts=attempts)
                    return {
                        "locator": locator,
                        "target_percent": target_percent,
                        "attempts": attempts,
                        "dismissed_overlays": dismissed,
                    }

                if self._is_within_tolerance(
                    ui_value,
                    target_percent,
                    tolerance_percent,
                ):
                    raise AssertionError(
                        f"Slider UI reached {ui_value!r}% but the independent source "
                        f"reported {independent_value!r}%"
                    )

                observed = ui_value if ui_value is not None else independent_value
                if observed is None:
                    raise SliderValueUnavailableError("No slider value was available after the drag")
                working_value = observed

            raise AssertionError(
                f"Expected slider {target_percent}% ± {tolerance_percent}%, "
                f"UI reported {ui_value!r}% and independent source reported "
                f"{independent_value!r}% after {max_attempts} attempts"
            )

        action = self._run("set-slider-value", operation, record_success=True)
        return SliderResult(
            action=action,
            target_percent=target_percent,
            ui_percent=outcome.get("ui"),
            independent_percent=outcome.get("independent"),
            attempts=outcome.get("attempts", max_attempts),
        )

    def _run(
        self,
        operation_name: str,
        operation: Callable[[], dict[str, Any]],
        *,
        record_success: bool | None = None,
    ) -> ActionResult:
        should_record = (
            self.record_successful_actions if record_success is None else record_success
        )
        started = monotonic()
        try:
            before = self.capture_state(f"{operation_name}-before") if should_record else None
            details = operation()
            after = self.capture_state(f"{operation_name}-after") if should_record else None
        except Exception as error:
            failure = self._capture_failure(f"{operation_name}-failure")
            raise AppiumActionError(
                operation_name,
                str(error) or error.__class__.__name__,
                evidence=failure,
            ) from error
        elapsed = monotonic() - started
        self.logger.info("%s completed in %.3fs", operation_name, elapsed)
        return ActionResult(
            operation=operation_name,
            elapsed_seconds=elapsed,
            details=details,
            evidence=ActionEvidence(before=before, after=after),
        )

    def _wait(self, timeout_seconds: float | None = None) -> WebDriverWait:
        timeout = self.default_timeout_seconds if timeout_seconds is None else timeout_seconds
        if timeout <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        return WebDriverWait(self.driver, timeout, poll_frequency=self.poll_seconds)

    def _wait_for_postcondition(
        self,
        postcondition: Callable[[], bool] | None,
        timeout_seconds: float | None,
    ) -> None:
        if postcondition is not None:
            self._wait(timeout_seconds).until(lambda _: bool(postcondition()))

    def _capture_failure(self, label: str) -> CapturedState | None:
        try:
            return self.capture_state(label)
        except Exception:
            self.logger.exception("Could not capture failure evidence for %s", label)
            return None

    def _dismiss_known_overlays(self, rules: Iterable[OverlayRule]) -> list[Locator]:
        dismissed: list[Locator] = []
        for rule in rules:
            visible_overlays = [
                element
                for element in self.driver.find_elements(*rule.container)
                if self._is_displayed(element)
            ]
            if not visible_overlays:
                continue
            if rule.dismiss is not None:
                self.find(
                    rule.dismiss,
                    state="clickable",
                    timeout_seconds=rule.timeout_seconds,
                ).click()
            self.wait_until_gone(rule.container, timeout_seconds=rule.timeout_seconds)
            dismissed.append(rule.container)
        return dismissed

    @staticmethod
    def _is_displayed(element: Any) -> bool:
        try:
            return bool(element.is_displayed())
        except StaleElementReferenceException:
            return False

    def _first_visible(self, locator: Locator) -> Any | None:
        for element in self.driver.find_elements(*locator):
            if self._is_displayed(element):
                return element
        return None

    def _tap_point(self, point: Point) -> None:
        self._touch(point, point, hold_seconds=0.05, move_duration_seconds=0)

    def _touch(
        self,
        start: Point,
        end: Point,
        *,
        hold_seconds: float,
        move_duration_seconds: float,
    ) -> None:
        duration_ms = max(0, round(move_duration_seconds * 1000))
        actions = ActionChains(self.driver)
        actions.w3c_actions = ActionBuilder(
            self.driver,
            mouse=PointerInput(interaction.POINTER_TOUCH, "finger"),
            duration=duration_ms,
        )
        pointer = actions.w3c_actions.pointer_action
        pointer.move_to_location(start.x, start.y)
        pointer.pointer_down()
        if hold_seconds:
            pointer.pause(hold_seconds)
        if end != start:
            pointer.move_to_location(end.x, end.y)
        pointer.release()
        actions.perform()

    def _assert_point_on_screen(self, point: Point) -> None:
        size = self.driver.get_window_size()
        if not 0 <= point.x < size["width"] or not 0 <= point.y < size["height"]:
            raise ValueError(
                f"Point {point} is outside screen {size['width']}x{size['height']}"
            )

    def _screen_fraction_to_point(self, value: tuple[float, float]) -> Point:
        x_fraction, y_fraction = value
        if not 0 <= x_fraction <= 1 or not 0 <= y_fraction <= 1:
            raise ValueError("Screen fractions must be between 0.0 and 1.0")
        size = self.driver.get_window_size()
        return Point(
            x=min(round(size["width"] * x_fraction), size["width"] - 1),
            y=min(round(size["height"] * y_fraction), size["height"] - 1),
        )

    def _scroll_points(self, direction: SwipeDirection) -> tuple[Point, Point]:
        paths = {
            "up": ((0.5, 0.8), (0.5, 0.2)),
            "down": ((0.5, 0.2), (0.5, 0.8)),
            "left": ((0.8, 0.5), (0.2, 0.5)),
            "right": ((0.2, 0.5), (0.8, 0.5)),
        }
        if direction not in paths:
            raise ValueError(f"Unsupported swipe direction: {direction}")
        start, end = paths[direction]
        return self._screen_fraction_to_point(start), self._screen_fraction_to_point(end)

    @staticmethod
    def _slider_points(
        rect: Rect,
        current_percent: float,
        target_percent: float,
        track_inset_percent: float,
    ) -> tuple[Point, Point]:
        if rect.width <= 0 or rect.height <= 0:
            raise ValueError(f"Slider has invalid bounds: {rect}")
        left = rect.x + rect.width * track_inset_percent / 100
        usable_width = rect.width * (1 - 2 * track_inset_percent / 100)
        center_y = round(rect.y + rect.height / 2)

        def point_for(value: float) -> Point:
            return Point(round(left + usable_width * value / 100), center_y)

        return point_for(current_percent), point_for(target_percent)

    def _try_slider_read(
        self,
        locator: Locator,
        reader: Callable[[Any], float],
    ) -> float | None:
        try:
            element = self._first_visible(locator)
            if element is None:
                return None
            value = float(reader(element))
        except (SliderValueUnavailableError, NoSuchElementException, StaleElementReferenceException):
            return None
        if not 0 <= value <= 100:
            raise ValueError(f"Slider reader returned {value}; expected 0 through 100")
        return value

    @staticmethod
    def _read_independent(reader: Callable[[], float] | None) -> float | None:
        if reader is None:
            return None
        value = float(reader())
        if not 0 <= value <= 100:
            raise ValueError(f"Independent reader returned {value}; expected 0 through 100")
        return value

    def _wait_for_slider_values(
        self,
        locator: Locator,
        value_reader: Callable[[Any], float],
        independent_reader: Callable[[], float] | None,
        target_percent: float,
        tolerance_percent: float,
        timeout_seconds: float,
    ) -> tuple[float | None, float | None]:
        latest: list[float | None] = [None, None]

        def values_match(_: Any) -> bool:
            latest[0] = self._try_slider_read(locator, value_reader)
            latest[1] = self._read_independent(independent_reader)
            return self._slider_values_match(
                target_percent,
                tolerance_percent,
                latest[0],
                latest[1],
            )

        try:
            WebDriverWait(
                self.driver,
                timeout_seconds,
                poll_frequency=self.poll_seconds,
            ).until(values_match)
        except TimeoutException:
            pass
        return latest[0], latest[1]

    @staticmethod
    def _slider_values_match(
        target: float,
        tolerance: float,
        ui_value: float | None,
        independent_value: float | None,
    ) -> bool:
        values = [value for value in (ui_value, independent_value) if value is not None]
        return bool(values) and all(abs(value - target) <= tolerance for value in values)

    @staticmethod
    def _is_within_tolerance(
        value: float | None,
        target: float,
        tolerance: float,
    ) -> bool:
        return value is not None and abs(value - target) <= tolerance
