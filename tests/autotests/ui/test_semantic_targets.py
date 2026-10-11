"""Deterministic tests for semantic target loading and locator diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentic_mobile_test.appium.models import CapturedState
from agentic_mobile_test.appium.targets import (
    AppiumTargetResolver,
    LocatorCandidate,
    LocatorResolutionError,
    SemanticTarget,
    TargetCatalog,
    TargetCatalogError,
)


def test_catalog_loads_ranked_semantic_targets() -> None:
    path = Path(__file__).with_name("targets") / "android_settings.json"

    catalog = TargetCatalog.load(path)
    target = catalog.require("settings.about_device")

    assert target.screen == "settings.home"
    assert target.source == path.resolve()
    assert target.preferred_locator == (
        "-android uiautomator",
        'new UiSelector().textMatches("^About (phone|emulated device)$")',
    )


def test_resolver_skips_ambiguous_locator_and_traces_unique_fallback(
    tmp_path: Path,
) -> None:
    first = ("accessibility id", "About phone")
    second = ("id", "com.example:id/about")
    driver = _Driver(
        {
            first: [_Element(), _Element()],
            second: [_Element()],
        }
    )
    actions = _Actions(driver, tmp_path)
    trace_path = tmp_path / "locator-trace.jsonl"
    resolver = AppiumTargetResolver(actions, trace_path=trace_path)
    target = _target(tmp_path, first, second)

    resolved = resolver.resolve(target, state="clickable", timeout_seconds=0)

    assert resolved.locator == second
    assert resolved.rank == 2
    assert [attempt.outcome for attempt in resolved.attempts] == [
        "ambiguous",
        "unique",
    ]
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["target_id"] == "settings.about_device"
    assert trace["catalog"] == str(target.source)
    assert trace["selected_rank"] == 2
    assert trace["attempts"][0]["eligible_matches"] == 2
    assert actions.capture_labels == []


def test_resolver_captures_state_and_reports_all_failed_candidates(
    tmp_path: Path,
) -> None:
    first = ("accessibility id", "About phone")
    second = ("id", "com.example:id/about")
    actions = _Actions(_Driver({}), tmp_path)
    trace_path = tmp_path / "locator-trace.jsonl"
    resolver = AppiumTargetResolver(actions, trace_path=trace_path)

    with pytest.raises(LocatorResolutionError, match="not_found") as captured:
        resolver.resolve(
            _target(tmp_path, first, second),
            state="visible",
            timeout_seconds=0,
        )

    assert len(captured.value.attempts) == 2
    assert captured.value.evidence is not None
    assert actions.capture_labels == ["locator-failure-settings.about_device"]
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["outcome"] == "not_resolved"
    assert trace["evidence"]["screenshot"].endswith("failure.png")


def test_catalog_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "targets": [],
                "unreviewed_option": True,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(TargetCatalogError, match="Unknown catalog fields"):
        TargetCatalog.load(path)


def _target(
    root: Path,
    first: tuple[str, str],
    second: tuple[str, str],
) -> SemanticTarget:
    return SemanticTarget(
        target_id="settings.about_device",
        screen="settings.home",
        locators=(
            LocatorCandidate(first[0], first[1], "preferred locator"),
            LocatorCandidate(second[0], second[1], "fallback locator"),
        ),
        source=(root / "targets.json").resolve(),
    )


class _Element:
    def __init__(self, *, displayed: bool = True, enabled: bool = True) -> None:
        self.displayed = displayed
        self.enabled = enabled

    def is_displayed(self) -> bool:
        return self.displayed

    def is_enabled(self) -> bool:
        return self.enabled


class _Driver:
    current_package = "com.android.settings"
    current_activity = ".Settings"

    def __init__(self, matches: dict[tuple[str, str], list[_Element]]) -> None:
        self.matches = matches

    def find_elements(self, strategy: str, value: str) -> list[_Element]:
        return self.matches.get((strategy, value), [])


class _Actions:
    default_timeout_seconds = 0.1
    poll_seconds = 0.01

    def __init__(self, driver: _Driver, evidence_dir: Path) -> None:
        self.driver = driver
        self.evidence_dir = evidence_dir
        self.capture_labels: list[str] = []

    def capture_state(self, label: str) -> CapturedState:
        self.capture_labels.append(label)
        screenshot = self.evidence_dir / "failure.png"
        ui_source = self.evidence_dir / "failure.xml"
        screenshot.write_bytes(b"image")
        ui_source.write_text("<hierarchy />", encoding="utf-8")
        return CapturedState(screenshot=screenshot, ui_source=ui_source)
