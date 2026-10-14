"""Offline tests for safe generation from recorded discovery evidence."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from agentic_mobile_test.generation import TestGenerationError, generate_test_candidate
from agentic_mobile_test.contracts import ActionKind
from agentic_mobile_test.generation.candidate import _render_action


def test_passed_discovery_generates_review_only_semantic_replay(tmp_path: Path) -> None:
    run_dir, scenario_path, catalog_path = _generation_inputs(tmp_path)

    output = generate_test_candidate(
        run_dir,
        scenario_path,
        target_catalog_path=catalog_path,
    )

    source = output.read_text(encoding="utf-8")
    ast.parse(source)
    assert output.name.endswith(".py.candidate")
    assert "device.ui.scroll_until_visible(\"settings.about_device\"" in source
    assert "device.ui.tap(\"settings.about_device\"" in source
    assert "TextVerifier().evaluate(scenario, final_observation)" in source
    assert "e003" not in source
    assert "new UiSelector" not in source
    assert "test_data" not in source


def test_generator_refuses_nonpassing_discovery(tmp_path: Path) -> None:
    run_dir, scenario_path, catalog_path = _generation_inputs(tmp_path)
    record_path = run_dir / "discovered-path.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["verification"]["checks"][0]["passed"] = False
    record_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(TestGenerationError, match="Every recorded"):
        generate_test_candidate(
            run_dir,
            scenario_path,
            target_catalog_path=catalog_path,
        )


def test_generator_refuses_changed_scenario_contract(tmp_path: Path) -> None:
    run_dir, scenario_path, catalog_path = _generation_inputs(tmp_path)
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario["goal"] = "Different expected behavior"
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")

    with pytest.raises(TestGenerationError, match="does not match"):
        generate_test_candidate(
            run_dir,
            scenario_path,
            target_catalog_path=catalog_path,
        )


def test_generator_refuses_evidence_hash_mismatch(tmp_path: Path) -> None:
    run_dir, scenario_path, catalog_path = _generation_inputs(tmp_path)
    record_path = run_dir / "discovered-path.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["steps"][0]["transition"]["before"]["screenshot_sha256"] = "0" * 64
    record_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(TestGenerationError, match="hash mismatch"):
        generate_test_candidate(
            run_dir,
            scenario_path,
            target_catalog_path=catalog_path,
        )


def test_launch_app_candidate_uses_approved_scenario_reference() -> None:
    lines = _render_action(
        {
            "action": ActionKind.LAUNCH_APP,
            "sequence": 1,
            "value_ref": "youtube",
        }
    )

    assert lines == ['    device.apps.launch(scenario.launchable_apps["youtube"])']


def _generation_inputs(root: Path) -> tuple[Path, Path, Path]:
    scenario_dir = root / "tests/autotests/ui/android_settings/scenarios"
    targets_dir = scenario_dir.parent / "targets"
    run_dir = root / "runs/discovery-1"
    evidence_dir = run_dir / "evidence"
    scenario_dir.mkdir(parents=True)
    targets_dir.mkdir()
    evidence_dir.mkdir(parents=True)

    scenario_path = scenario_dir / "about_phone.json"
    scenario = {
        "schema_version": 1,
        "scenario_id": "android-settings-about-phone",
        "scenario_type": "positive",
        "goal": "Open Android Settings About phone",
        "preconditions": ["Settings is at its root"],
        "cleanup": ["Return Settings to its root"],
        "assertions": [
            {
                "assertion_id": "device-name",
                "text": "Device name",
                "exact": True,
                "expectation": "visible",
            }
        ],
        "allowed_actions": ["scroll_forward", "tap"],
        "test_data": {},
        "launchable_apps": {},
        "max_steps": 3,
    }
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")

    catalog_path = targets_dir / "android_settings.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "targets": [
                    {
                        "id": "settings.about_device",
                        "screen": "settings.home",
                        "locators": [
                            {
                                "strategy": "accessibility id",
                                "value": "About phone",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    transitions = []
    for step in (1, 2):
        transition: dict[str, Any] = {}
        for phase in ("before", "after"):
            screenshot = evidence_dir / f"{step}-{phase}.png"
            ui_source = evidence_dir / f"{step}-{phase}.xml"
            screenshot.write_bytes(f"screen-{step}-{phase}".encode())
            ui_source.write_text("<hierarchy />", encoding="utf-8")
            transition[phase] = {
                "screenshot": str(screenshot.relative_to(run_dir)),
                "screenshot_sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest(),
                "ui_source": str(ui_source.relative_to(run_dir)),
                "ui_source_sha256": hashlib.sha256(ui_source.read_bytes()).hexdigest(),
            }
        transitions.append(transition)

    discovered = {
        "schema_version": 1,
        "record_type": "successful_ui_path",
        "generation_status": "candidate_requires_review",
        "scenario": {
            "schema_version": 1,
            "scenario_id": scenario["scenario_id"],
            "scenario_type": scenario["scenario_type"],
            "goal": scenario["goal"],
            "preconditions": scenario["preconditions"],
            "cleanup": scenario["cleanup"],
            "assertions": scenario["assertions"],
            "allowed_actions": sorted(scenario["allowed_actions"]),
            "launchable_apps": scenario["launchable_apps"],
            "test_data_refs": [],
            "max_steps": scenario["max_steps"],
        },
        "steps": [
            {
                "sequence": 1,
                "action": {"name": "scroll_forward", "target": None, "value_ref": None},
                "transition": transitions[0],
            },
            {
                "sequence": 2,
                "action": {
                    "name": "tap",
                    "target": {
                        "observed_ref": "e003",
                        "label": "About phone",
                        "locator_candidate": {
                            "strategy": "accessibility id",
                            "value": "About phone",
                        },
                    },
                    "value_ref": None,
                },
                "transition": transitions[1],
            },
        ],
        "verification": {
            "state": "passed",
            "checks": [{"assertion_id": "device-name", "passed": True}],
            "summary": "All approved assertions are satisfied",
        },
    }
    (run_dir / "discovered-path.json").write_text(
        json.dumps(discovered),
        encoding="utf-8",
    )
    return run_dir, scenario_path, catalog_path
