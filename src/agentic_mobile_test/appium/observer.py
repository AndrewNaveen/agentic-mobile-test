"""Turn Appium screenshots and UI hierarchy XML into planner-safe observations."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from typing import Any
from xml.etree import ElementTree

from ..contracts import Observation, ObservedElement
from .actions import AppiumActions


class ObservationError(RuntimeError):
    """The current device state could not be captured or interpreted."""


class AppiumObserver:
    def __init__(self, actions: AppiumActions) -> None:
        self.actions = actions
        self._sequence = 0

    def observe(self) -> Observation:
        self._sequence += 1
        state = self.actions.capture_state(f"observation-{self._sequence:03d}")
        try:
            root = ElementTree.parse(state.ui_source).getroot()
        except (OSError, ElementTree.ParseError) as error:
            raise ObservationError(f"Unable to parse Appium UI source: {error}") from error

        nodes = list(root.iter())
        content_desc_counts = Counter(_attribute(node, "content-desc") for node in nodes)
        resource_id_counts = Counter(_attribute(node, "resource-id") for node in nodes)
        text_counts = Counter(_attribute(node, "text") for node in nodes)
        elements: list[ObservedElement] = []

        clickable_nodes = _nodes_with_clickable_ancestor(root)
        for node in nodes:
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
                    locator_strategy=strategy,
                    locator_value=locator,
                )
            )

        app_package = _driver_value(self.actions.driver, "current_package")
        activity = _driver_value(self.actions.driver, "current_activity")
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
            }
            for element in elements
        ],
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _attribute(node: ElementTree.Element, name: str) -> str:
    return str(node.attrib.get(name, "")).strip()


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


def _driver_value(driver: Any, name: str) -> str | None:
    try:
        value = getattr(driver, name)
    except Exception:
        return None
    return str(value) if value else None
