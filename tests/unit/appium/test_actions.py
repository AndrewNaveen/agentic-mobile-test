"""Common Appium action wait helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from selenium.common.exceptions import TimeoutException

from agentic_mobile_test.appium.actions import AppiumActions


@pytest.mark.parametrize(
    ("method_name", "expected_state"),
    [
        ("wait_until_present", "present"),
        ("wait_until_visible", "visible"),
        ("wait_until_enabled", "enabled"),
        ("wait_until_clickable", "clickable"),
    ],
)
def test_wait_helpers_delegate_to_bounded_find_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    expected_state: str,
) -> None:
    actions = AppiumActions(object(), evidence_dir=tmp_path)
    calls: list[dict[str, Any]] = []

    def found(locator: tuple[str, str], **kwargs: Any) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(actions, "find", found)

    assert getattr(actions, method_name)(("id", "retry"), timeout_seconds=30)
    assert calls == [{"state": expected_state, "timeout_seconds": 30}]


def test_wait_helper_returns_false_after_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions = AppiumActions(object(), evidence_dir=tmp_path)

    def timeout(*_: Any, **__: Any) -> None:
        raise TimeoutException("not ready")

    monkeypatch.setattr(actions, "find", timeout)

    assert not actions.wait_until_visible(("id", "retry"), timeout_seconds=0.01)
