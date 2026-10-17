"""Turn Appium screenshots and UI hierarchy XML into planner-safe observations."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from time import monotonic
from typing import Any
from xml.etree import ElementTree

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from ..contracts import Observation, ObservedElement
from .actions import AppiumActions


class ObservationError(RuntimeError):
    """The current device state could not be captured or interpreted."""


class AppiumObserver:
    def __init__(
        self, actions: AppiumActions, *, settle_timeout_seconds: float = 10.0,
        stable_seconds: float = 0.6, poll_seconds: float = 0.2,
    ) -> None:
        if not 0 < stable_seconds < settle_timeout_seconds or poll_seconds <= 0:
            raise ValueError("Require 0 < stable_seconds < settle_timeout_seconds and positive polling")
        self.actions = actions
        self.settle_timeout_seconds = settle_timeout_seconds
        self.stable_seconds = stable_seconds
        self.poll_seconds = poll_seconds
        self._sequence = 0

    def observe(self) -> Observation:
        self._sequence += 1
        state, root, app_package, activity = self._settled_capture()

        nodes = list(root.iter())
        content_desc_counts = Counter(_attribute(node, "content-desc") for node in nodes)
        resource_id_counts = Counter(_attribute(node, "resource-id") for node in nodes)
        text_counts = Counter(_attribute(node, "text") for node in nodes)
        elements: list[ObservedElement] = []

        clickable_nodes = _nodes_with_clickable_ancestor(root)
        toggle_targets = _toggle_targets(root)
        parents = {child: parent for parent in root.iter() for child in parent}
        visible_nodes = _visible_nodes(root)
        for node in nodes:
            if id(node) not in visible_nodes:
                continue
            text = _attribute(node, "text")
            accessibility_id = _attribute(node, "content-desc")
            resource_id = _attribute(node, "resource-id")
            class_name = _attribute(node, "class")
            clickable = id(node) in clickable_nodes
            enabled = _boolean_attribute(node, "enabled", default=True)
            if not any((text, accessibility_id, resource_id, clickable)):
                continue

            strategy, locator = _safe_locator(
                text=text,
                accessibility_id=accessibility_id,
                resource_id=resource_id,
                content_desc_counts=content_desc_counts,
                resource_id_counts=resource_id_counts,
                text_counts=text_counts,
            )
            elements.append(
                ObservedElement(
                    ref=f"e{len(elements) + 1:03d}",
                    label=text or accessibility_id or resource_id or class_name,
                    text=text,
                    accessibility_id=accessibility_id,
                    resource_id=resource_id,
                    class_name=class_name,
                    clickable=clickable,
                    enabled=enabled,
                    checked=(
                        _boolean_attribute(node, "checked")
                        if _boolean_attribute(node, "checkable")
                        and node.attrib.get("checked") in {"true", "false"}
                        else None
                    ),
                    toggles_state=id(node) in toggle_targets,
                    checkable=_boolean_attribute(node, "checkable"),
                    toggle_labels=_toggle_labels(node, parents, visible_nodes),
                    locator_strategy=strategy,
                    locator_value=locator,
                )
            )

        fingerprint = _fingerprint(app_package, activity, elements)
        return Observation(
            sequence=self._sequence,
            fingerprint=fingerprint,
            screenshot=state.screenshot,
            ui_source=state.ui_source,
            elements=tuple(elements),
            app_package=app_package,
            activity=activity,
        )

    def _settled_capture(self) -> tuple[Any, ElementTree.Element, str | None, str | None]:
        """Require repeated image AND hierarchy agreement, not just foreground status.

        Intermediate captures remain diagnostic files. Only the accepted sample
        becomes an Observation and is copied into the successful discovery path.
        Appium commands have their own transport timeouts; this bounds polling.
        """
        previous = None
        stable_since = monotonic()
        started = stable_since
        samples = 0
        last_state = None

        def settled(driver: Any) -> Any:
            nonlocal previous, stable_since, samples, last_state
            samples += 1
            before = (_driver_value(driver, "current_package"), _driver_value(driver, "current_activity"))
            state = self.actions.capture_state(
                f"observation-{self._sequence:03d}-settle-{samples:03d}"
            )
            last_state = state
            try:
                source = state.ui_source.read_text(encoding="utf-8")
                root = ElementTree.fromstring(source)
                image_hash = sha256(state.screenshot.read_bytes()).hexdigest()
            except (OSError, ElementTree.ParseError) as error:
                raise ObservationError(f"Unable to read observation evidence: {error}") from error
            after = (_driver_value(driver, "current_package"), _driver_value(driver, "current_activity"))
            # Include bounds and checked state, not only planner-facing labels.
            signature = (image_hash, ElementTree.canonicalize(source), after)
            now = monotonic()
            if before != after or signature != previous:
                stable_since = now
                previous = signature if before == after else None
                return False
            if now - started >= self.settle_timeout_seconds:
                return False
            if now - stable_since < self.stable_seconds:
                return False
            return state, root, *after

        try:
            return WebDriverWait(
                self.actions.driver, self.settle_timeout_seconds,
                poll_frequency=self.poll_seconds,
            ).until(settled)
        except TimeoutException as error:
            evidence = f" Last capture: {last_state.screenshot}" if last_state else ""
            raise ObservationError(
                f"Screen did not settle within {self.settle_timeout_seconds:g}s "
                f"({samples} samples); no transition frame was sent to the planner.{evidence}"
            ) from error

    def wait_for_clickable_text(
        self,
        text: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> Observation:
        """Wait a bounded time for a visible UI label to become actionable."""

        if not text.strip():
            raise ValueError("text must be non-empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        expected = _normalize(text)
        try:
            WebDriverWait(
                self.actions.driver,
                timeout_seconds,
                poll_frequency=self.actions.poll_seconds,
            ).until(
                lambda driver: _has_enabled_clickable_text(driver.page_source, expected)
            )
        except TimeoutException as error:
            _capture_timeout(self.actions, text)
            raise ObservationError(
                f"UI target {text!r} did not become enabled and clickable "
                f"within {timeout_seconds:g} seconds"
            ) from error
        return self.observe()


def _safe_locator(
    *,
    text: str,
    accessibility_id: str,
    resource_id: str,
    content_desc_counts: Counter[str],
    resource_id_counts: Counter[str],
    text_counts: Counter[str],
) -> tuple[str | None, str | None]:
    if accessibility_id and content_desc_counts[accessibility_id] == 1:
        return "accessibility id", accessibility_id
    if resource_id and resource_id_counts[resource_id] == 1:
        return "id", resource_id
    if text and text_counts[text] == 1:
        return "-android uiautomator", f"new UiSelector().text({json.dumps(text)})"
    return None, None


def _fingerprint(
    app_package: str | None,
    activity: str | None,
    elements: list[ObservedElement],
) -> str:
    value = {
        "app_package": app_package,
        "activity": activity,
        "elements": [
            {
                "text": element.text,
                "accessibility_id": element.accessibility_id,
                "resource_id": element.resource_id,
                "class_name": element.class_name,
                "clickable": element.clickable,
                "enabled": element.enabled,
                "checked": element.checked,
                "toggles_state": element.toggles_state,
            }
            for element in elements
        ],
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _attribute(node: ElementTree.Element, name: str) -> str:
    return str(node.attrib.get(name, "")).strip()


def _toggle_targets(root: ElementTree.Element) -> set[int]:
    """Protect switches plus their clickable row labels from verification taps."""
    parents = {child: parent for parent in root.iter() for child in parent}
    protected: set[int] = set()
    for node in root.iter():
        if not _boolean_attribute(node, "checkable"):
            continue
        protected.update(id(child) for child in node.iter())
        parent = parents.get(node)
        while parent is not None:
            if _boolean_attribute(parent, "clickable"):
                protected.update(id(child) for child in parent.iter())
                break
            parent = parents.get(parent)
    return protected


def _toggle_labels(
    node: ElementTree.Element, parents: dict[ElementTree.Element, ElementTree.Element],
    visible_nodes: set[int],
) -> tuple[str, ...]:
    """Associate a switch with labels in its immediate row, never the whole page."""
    if not _boolean_attribute(node, "checkable"):
        return ()
    parent = parents.get(node)
    if parent is None or sum(_boolean_attribute(child, "checkable") for child in parent.iter()) != 1:
        return ()
    return tuple(dict.fromkeys(
        value for child in parent.iter()
        for value in (_attribute(child, "text"), _attribute(child, "content-desc"))
        if value and id(child) in visible_nodes
    ))


def _visible_nodes(root: ElementTree.Element) -> set[int]:
    """A hidden ancestor hides its entire subtree, even without child attributes."""
    visible: set[int] = set()

    def visit(node: ElementTree.Element) -> None:
        if any(node.attrib.get(name, "true").lower() == "false"
               for name in ("displayed", "visible")):
            return
        visible.add(id(node))
        for child in node:
            visit(child)

    visit(root)
    return visible


def _boolean_attribute(
    node: ElementTree.Element,
    name: str,
    *,
    default: bool = False,
) -> bool:
    raw = node.attrib.get(name)
    return default if raw is None else str(raw).lower() == "true"


def _nodes_with_clickable_ancestor(root: ElementTree.Element) -> set[int]:
    """Include text children whose containing Android row owns the click."""

    clickable_nodes: set[int] = set()

    def visit(node: ElementTree.Element, ancestor_clickable: bool) -> None:
        clickable = ancestor_clickable or _boolean_attribute(node, "clickable")
        if clickable:
            clickable_nodes.add(id(node))
        for child in node:
            visit(child, clickable)

    visit(root, False)
    return clickable_nodes


def _has_enabled_clickable_text(source: str, expected: str) -> bool:
    try:
        root = ElementTree.fromstring(source)
    except ElementTree.ParseError:
        return False
    for node in root.iter():
        if _normalize(_attribute(node, "text")) != expected:
            continue
        if _boolean_attribute(node, "enabled") and _boolean_attribute(node, "clickable"):
            return True
        parent_clickable = _has_clickable_ancestor(node, root)
        if _boolean_attribute(node, "enabled") and parent_clickable:
            return True
    return False


def _has_clickable_ancestor(node: ElementTree.Element, root: ElementTree.Element) -> bool:
    parents = {child: parent for parent in root.iter() for child in parent}
    current = parents.get(node)
    while current is not None:
        if _boolean_attribute(current, "clickable") and _boolean_attribute(current, "enabled"):
            return True
        current = parents.get(current)
    return False


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _capture_timeout(actions: AppiumActions, text: str) -> None:
    try:
        actions.capture_state(f"target-not-clickable-{text}")
    except Exception:
        pass


def _driver_value(driver: Any, name: str) -> str | None:
    try:
        value = getattr(driver, name)
    except Exception:
        return None
    return str(value) if value else None
