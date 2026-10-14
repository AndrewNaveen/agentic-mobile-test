"""Validated conversion from a successful UI discovery record to pytest code."""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
from typing import Any

from ..appium.targets import TargetCatalog
from ..contracts import ActionKind, Scenario

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_]+")


class TestGenerationError(ValueError):
    """The discovery record is incomplete or cannot be replayed safely."""

    __test__ = False


def generate_test_candidate(
    run_directory: Path,
    scenario_path: Path,
    *,
    target_catalog_path: Path | None = None,
    target_map_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """Write a non-collected ``.py.candidate`` regression for engineer review."""
    run_directory = Path(run_directory).resolve()
    scenario_path = Path(scenario_path).resolve()
    discovery_path = run_directory / "discovered-path.json"
    discovery = _read_json(discovery_path)
    scenario = Scenario.load(scenario_path)
    _validate_discovery(discovery, scenario, run_directory)

    if target_catalog_path is None:
        target_catalog_path = scenario_path.parent.parent / "targets/android_settings.json"
    catalog = TargetCatalog.load(Path(target_catalog_path))
    supplied_map = _load_target_map(target_map_path) if target_map_path else {}
    steps = _validated_steps(discovery["steps"], scenario, catalog, supplied_map)

    ui_test_directory = scenario_path.parent.parent
    if output_path is None:
        output_path = ui_test_directory / f"test_{_slug(scenario.scenario_id)}.py.candidate"
    output_path = Path(output_path).resolve()
    if output_path.parent != ui_test_directory.resolve():
        raise TestGenerationError(
            "Candidate must be beside its Android Settings scenario so its relative "
            "scenario reference stays valid"
        )
    if output_path.suffixes[-2:] != [".py", ".candidate"]:
        raise TestGenerationError("Candidate filename must end in '.py.candidate'")
    if output_path.exists():
        raise TestGenerationError(f"Refusing to overwrite candidate: {output_path}")

    source = _render_test(scenario, scenario_path, output_path, steps)
    try:
        ast.parse(source, filename=str(output_path))
    except SyntaxError as error:
        raise TestGenerationError(f"Generated pytest candidate is invalid: {error}") from error

    output_path.write_text(source, encoding="utf-8")
    return output_path


def _validate_discovery(
    discovery: dict[str, Any],
    scenario: Scenario,
    run_directory: Path,
) -> None:
    if discovery.get("schema_version") != 1:
        raise TestGenerationError("Only discovery schema_version 1 is supported")
    if discovery.get("record_type") != "successful_ui_path":
        raise TestGenerationError("Input is not a successful UI path record")
    if discovery.get("generation_status") != "candidate_requires_review":
        raise TestGenerationError("Discovery record is not marked for human review")

    recorded_scenario = discovery.get("scenario")
    if not isinstance(recorded_scenario, dict):
        raise TestGenerationError("Discovery record is missing its scenario contract")
    if not _scenario_matches(recorded_scenario, scenario):
        raise TestGenerationError(
            "Scenario JSON does not match the contract recorded during discovery"
        )

    verification = discovery.get("verification")
    if not isinstance(verification, dict) or verification.get("state") != "passed":
        raise TestGenerationError("Only discovery runs with passed verification can generate tests")
    checks = verification.get("checks")
    if not isinstance(checks, list) or not checks:
        raise TestGenerationError("Discovery record has no deterministic assertion checks")
    if any(not isinstance(check, dict) or check.get("passed") is not True for check in checks):
        raise TestGenerationError("Every recorded deterministic assertion must have passed")

    steps = discovery.get("steps")
    if not isinstance(steps, list) or len(steps) > scenario.max_steps:
        raise TestGenerationError("Discovery step list is invalid or exceeds the scenario budget")
    if not steps:
        raise TestGenerationError("Discovery path contains no executable steps")
    for step in steps:
        if not isinstance(step, dict):
            raise TestGenerationError("Every discovery step must be an object")
        transition = step.get("transition")
        if not isinstance(transition, dict):
            raise TestGenerationError("Every discovery step must include transition evidence")
        for phase in ("before", "after"):
            evidence = transition.get(phase)
            if not isinstance(evidence, dict):
                raise TestGenerationError(f"Discovery step is missing {phase} evidence")
            _verify_evidence(run_directory, evidence, "screenshot")
            _verify_evidence(run_directory, evidence, "ui_source")


def _scenario_matches(record: dict[str, Any], scenario: Scenario) -> bool:
    expected_assertions = [
        {
            "assertion_id": item.assertion_id,
            "text": item.text,
            "exact": item.exact,
            "expectation": item.expectation.value,
        }
        for item in scenario.assertions
    ]
    return (
        record.get("schema_version") == 1
        and record.get("scenario_id") == scenario.scenario_id
        and record.get("scenario_type") == scenario.scenario_type.value
        and record.get("goal") == scenario.goal
        and record.get("preconditions") == list(scenario.preconditions)
        and record.get("cleanup") == list(scenario.cleanup)
        and record.get("assertions") == expected_assertions
        and record.get("allowed_actions")
        == sorted(action.value for action in scenario.allowed_actions)
        and record.get("launchable_apps") == dict(scenario.launchable_apps)
        and record.get("test_data_refs") == sorted(scenario.test_data)
        and record.get("max_steps") == scenario.max_steps
    )


def _verify_evidence(run_directory: Path, evidence: dict[str, Any], kind: str) -> None:
    relative_path = evidence.get(kind)
    expected_hash = evidence.get(f"{kind}_sha256")
    if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
        raise TestGenerationError(f"Discovery {kind} reference or SHA-256 is missing")
    candidate = (run_directory / relative_path).resolve()
    if not candidate.is_relative_to(run_directory):
        raise TestGenerationError(f"Discovery {kind} path escapes its run directory")
    try:
        from hashlib import sha256

        actual_hash = sha256(candidate.read_bytes()).hexdigest()
    except OSError as error:
        raise TestGenerationError(f"Discovery evidence is unavailable: {relative_path}") from error
    if actual_hash != expected_hash:
        raise TestGenerationError(f"Discovery evidence hash mismatch: {relative_path}")


def _load_target_map(path: Path | None) -> dict[int, str]:
    if path is None:
        return {}
    document = _read_json(Path(path))
    if set(document) != {"schema_version", "step_targets"} or document.get("schema_version") != 1:
        raise TestGenerationError(
            "Target map must contain only schema_version=1 and step_targets"
        )
    raw_targets = document["step_targets"]
    if not isinstance(raw_targets, dict):
        raise TestGenerationError("step_targets must map discovery step numbers to target ids")
    targets: dict[int, str] = {}
    for raw_step, target_id in raw_targets.items():
        try:
            step_number = int(raw_step)
        except (TypeError, ValueError) as error:
            raise TestGenerationError(f"Invalid target-map step number: {raw_step!r}") from error
        if step_number < 1 or not isinstance(target_id, str) or not target_id.strip():
            raise TestGenerationError("Target-map entries require positive steps and target ids")
        targets[step_number] = target_id.strip()
    return targets


def _validated_steps(
    raw_steps: list[Any],
    scenario: Scenario,
    catalog: TargetCatalog,
    supplied_map: dict[int, str],
) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    action_target_steps: set[int] = set()
    previous_step = 0
    for raw in raw_steps:
        if not isinstance(raw, dict) or not isinstance(raw.get("sequence"), int):
            raise TestGenerationError("Discovery steps require an integer sequence")
        sequence = raw["sequence"]
        if sequence <= previous_step:
            raise TestGenerationError("Discovery step sequence must be strictly increasing")
        previous_step = sequence
        action_data = raw.get("action")
        if not isinstance(action_data, dict):
            raise TestGenerationError(f"Discovery step {sequence} has no action")
        try:
            action = ActionKind(action_data.get("name"))
        except ValueError as error:
            raise TestGenerationError(
                f"Discovery step {sequence} uses an unsupported action"
            ) from error
        if action not in scenario.allowed_actions:
            raise TestGenerationError(
                f"Discovery step {sequence} uses disallowed action {action.value!r}"
            )
        parsed.append({"sequence": sequence, "action": action, "value_ref": action_data.get("value_ref")})
        if action in {
            ActionKind.TAP,
            ActionKind.TYPE_TEXT,
            ActionKind.SCROLL_FORWARD,
            ActionKind.SCROLL_BACKWARD,
        }:
            action_target_steps.add(sequence)

    extra_mappings = set(supplied_map) - action_target_steps
    if extra_mappings:
        raise TestGenerationError(f"Target map contains unused steps: {sorted(extra_mappings)}")

    target_ids: dict[int, str] = {}
    for index, step in enumerate(parsed):
        sequence = step["sequence"]
        action: ActionKind = step["action"]
        if sequence in supplied_map:
            target_id = supplied_map[sequence]
            catalog.require(target_id)
            target_ids[sequence] = target_id
            continue
        if action in {ActionKind.TAP, ActionKind.TYPE_TEXT}:
            target = _target_record(raw_steps[index], sequence)
            locator = target.get("locator_candidate") if target else None
            if isinstance(locator, dict):
                strategy, value = locator.get("strategy"), locator.get("value")
                if isinstance(strategy, str) and isinstance(value, str):
                    matches = catalog.matching_ids((strategy, value))
                    if len(matches) == 1:
                        target_ids[sequence] = matches[0]
            if sequence not in target_ids:
                description = target.get("label") if target else "missing observed target"
                raise TestGenerationError(
                    f"Step {sequence} target {description!r} does not uniquely match the "
                    "reviewed target catalog; supply --target-map"
                )

    for index, step in enumerate(parsed):
        action: ActionKind = step["action"]
        if action in {ActionKind.SCROLL_FORWARD, ActionKind.SCROLL_BACKWARD}:
            sequence = step["sequence"]
            if sequence not in target_ids:
                next_target = next(
                    (
                        target_ids[item["sequence"]]
                        for item in parsed[index + 1 :]
                        if item["sequence"] in target_ids
                    ),
                    None,
                )
                if next_target is None:
                    raise TestGenerationError(
                        f"Scroll step {sequence} has no mapped semantic target; supply --target-map"
                    )
                target_ids[sequence] = next_target
        step["target_id"] = target_ids.get(step["sequence"])
        if action is ActionKind.TYPE_TEXT:
            value_ref = step["value_ref"]
            if not isinstance(value_ref, str) or value_ref not in scenario.test_data:
                raise TestGenerationError(
                    f"Type-text step {step['sequence']} references unavailable test data"
                )
        if action is ActionKind.LAUNCH_APP:
            value_ref = step["value_ref"]
            if not isinstance(value_ref, str) or value_ref not in scenario.launchable_apps:
                raise TestGenerationError(
                    f"Launch-app step {step['sequence']} references an unapproved app"
                )
    return parsed


def _target_record(step: dict[str, Any], sequence: int) -> dict[str, Any] | None:
    action = step.get("action")
    target = action.get("target") if isinstance(action, dict) else None
    return target if isinstance(target, dict) else None


def _render_test(
    scenario: Scenario,
    scenario_path: Path,
    output_path: Path,
    steps: list[dict[str, Any]],
) -> str:
    relative_scenario = Path(os.path.relpath(scenario_path, output_path.parent))
    scenario_literal = json.dumps(relative_scenario.as_posix())
    test_name = f"test_{_slug(scenario.scenario_id)}"
    lines = [
        '"""Deterministic regression candidate generated from reviewed discovery."""',
        "",
        "from pathlib import Path",
        "from typing import Any",
        "",
        "import pytest",
        "",
        "from agentic_mobile_test.appium.observer import AppiumObserver",
        "from agentic_mobile_test.contracts import Scenario, VerificationState",
        "from agentic_mobile_test.verification.verifier import TextVerifier",
        "",
        f"SCENARIO_PATH = Path(__file__).parent / {scenario_literal}",
        "",
        "",
        "@pytest.mark.appium",
        f"def {test_name}(android_settings_environment: Any) -> None:",
        '    """Replay the reviewed path and assert the fixed scenario oracle."""',
        "    # Arrange: the UI fixture establishes and restores the Settings root.",
        "    scenario = Scenario.load(SCENARIO_PATH)",
        "    device = android_settings_environment.device",
        "",
        "    # Act: replay reviewed semantic actions, never captured ephemeral refs.",
    ]
    for step in steps:
        lines.extend(_render_action(step))
    lines.extend(
        [
            "",
            "    # Assert: the same deterministic oracle used during discovery decides the result.",
            "    final_observation = AppiumObserver(device.actions).observe()",
            "    verification = TextVerifier().evaluate(scenario, final_observation)",
            "    assert verification.state is VerificationState.PASSED, verification.summary",
            "",
        ]
    )
    return "\n".join(lines)


def _render_action(step: dict[str, Any]) -> list[str]:
    action: ActionKind = step["action"]
    sequence = step["sequence"]
    target_id = step.get("target_id")
    if action is ActionKind.TAP:
        return [f"    device.ui.tap({json.dumps(target_id)}, timeout_seconds=10)"]
    if action is ActionKind.TYPE_TEXT:
        return [
            f"    device.ui.type_text({json.dumps(target_id)}, scenario.test_data["
            f"{json.dumps(step['value_ref'])}], timeout_seconds=10)"
        ]
    if action is ActionKind.SCROLL_FORWARD:
        return [
            f"    device.ui.scroll_until_visible({json.dumps(target_id)}, ",
            '        direction="up", max_swipes=8)',
        ]
    if action is ActionKind.SCROLL_BACKWARD:
        return [
            f"    device.ui.scroll_until_visible({json.dumps(target_id)}, ",
            '        direction="down", max_swipes=8)',
        ]
    if action is ActionKind.PRESS_BACK:
        return ["    device.actions.press_back(timeout_seconds=10)"]
    if action is ActionKind.LAUNCH_APP:
        return [
            "    device.apps.launch(scenario.launchable_apps["
            f"{json.dumps(step['value_ref'])}])"
        ]
    raise TestGenerationError(f"Cannot render action at step {sequence}: {action.value}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise TestGenerationError(f"Unable to read {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise TestGenerationError(f"Invalid JSON in {path}: {error}") from error
    if not isinstance(value, dict):
        raise TestGenerationError(f"Expected a JSON object in {path}")
    return value


def _slug(value: str) -> str:
    slug = _SAFE_NAME.sub("_", value).strip("_").lower()
    return slug or "scenario"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a review-only pytest candidate from a passed UI discovery run."
    )
    parser.add_argument("run_directory", type=Path, help="Directory containing discovered-path.json")
    parser.add_argument("--scenario", required=True, type=Path, help="Original reviewed scenario JSON")
    parser.add_argument("--target-catalog", type=Path, help="Reviewed semantic target catalog")
    parser.add_argument(
        "--target-map",
        type=Path,
        help="Optional JSON mapping discovery step numbers to reviewed semantic target ids",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Candidate path ending in .py.candidate (defaults beside the scenario)",
    )
    args = parser.parse_args()
    try:
        candidate = generate_test_candidate(
            args.run_directory,
            args.scenario,
            target_catalog_path=args.target_catalog,
            target_map_path=args.target_map,
            output_path=args.output,
        )
    except TestGenerationError as error:
        parser.error(str(error))
    print(f"Review candidate written to {candidate}")
    return 0
