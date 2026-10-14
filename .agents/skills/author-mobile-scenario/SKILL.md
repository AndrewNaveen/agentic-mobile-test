---
name: author-mobile-scenario
description: Turn a user's plain-language Android mobile UI test idea into a reviewed Agentic Mobile Test scenario JSON file. Use when defining, drafting, or revising a positive, negative, or edge UI scenario for this repository.
---

# Author a mobile test scenario

Convert the user's requested behavior into this repository's current scenario contract. The result is a scenario file for the existing pytest discovery runner, not a test implementation and not an instruction to run Appium or Gemini.

## Inspect before drafting

From the repository root, read:

- `docs/workflow/README.md` for the current end-to-end process and known limitations.
- `docs/workflow/scenario-template.json` for the current JSON shape.
- `src/agentic_mobile_test/contracts.py` for parser rules and supported action/assertion types.
- `tests/autotests/ui/android_settings/test_agentic_android_settings.py` and `tests/autotests/ui/conftest.py` for current collection and fixture behavior.

Do not assume a field described in prose is implemented by a fixture. In particular, `preconditions` and `cleanup` are descriptive only unless the current fixture has executable setup/teardown for them. The current shared live fixture is Android Settings-specific.

## Resolve missing product decisions

Before creating a runnable scenario, ensure the request supplies or clearly implies:

- The user-visible goal and whether it is positive, negative, or edge behavior.
- Initial state and required installed app(s).
- Expected outcome expressed as observable UI text that the deterministic verifier currently supports.
- Any important action that must happen before passing, such as tapping a result button.
- State that must be restored after the test.

For every scenario, separate these three things:

- **Allowed actions:** what the runtime agent is permitted to do.
- **Required interactions:** mandatory taps or text entry that must happen before the test can pass.
- **Final assertions:** deterministic evidence that the expected product behavior occurred.

Do not treat an action in `allowed_actions` or a sentence in `goal` as proof that the action happened. The current schema supports optional `required_interactions`, each identifying a required `tap` or `type_text`, target text, and minimum count. The runner blocks success until those interactions execute. Add this field when a specific interaction must happen even if final assertion text is already visible. Do not invent an interaction target: use text visible in the UI, and ask if it is unknown. Required interactions are not a general ordered-checkpoint system; final assertions must still establish the expected result. Launches, device state, and other non-UI effects need a deterministic state check or test fixture when essential.

Model optional branches explicitly in the scenario intent (for example, dismiss a permission prompt only if it appears); do not make optional UI part of the mandatory path. For each required interaction, confirm what deterministic assertion or state check proves the expected product result. If the product response to an interaction is unspecified or unobservable, ask for that expected behavior rather than inventing it.

Ask a concise follow-up when an expected result or destructive state change is ambiguous. Never invent product behavior, expected error messages, app package IDs, credentials, or cleanup guarantees. If the contract cannot express an important requirement (for example, enabled-state verification or a mandatory tap followed by a result check), say so and do not imply the JSON fully covers it.

## Write the scenario

1. Copy the structure from `docs/workflow/scenario-template.json`.
2. Save the completed file under `tests/autotests/ui/android_settings/scenarios/<descriptive-name>.json` for journeys that start in Android Settings. Do not overwrite another scenario.
3. Use a unique kebab-case `scenario_id`; keep it consistent with the filename.
4. Keep the `goal` in user language. The planner chooses one action per observation; do not write a speculative action list into `goal`.
5. Restrict `allowed_actions` to the minimum needed. Supported values are `tap`, `type_text`, `launch_app`, `scroll_forward`, `scroll_backward`, and `press_back`.
6. For `launch_app`, add a reviewed alias-to-package mapping in `launchable_apps` (for example, `{"youtube": "com.google.android.youtube"}`). Never guess an app ID; ask or verify from repository/device evidence.
7. Use fixed assertions for facts the current text verifier can check (`visible` or `absent` text). Do not ask the model to decide whether the test passed.
8. Keep secrets out of scenario JSON. Use named `test_data` references only when text entry is needed.
9. Choose a bounded `max_steps` no greater than 50; each discovery step may make one paid model call.
10. Before handing off, state which required interactions are enforced by `required_interactions` and which preconditions, cleanup, or outcomes depend on deterministic setup/assertions outside the agent loop. Never imply descriptive JSON text alone enforces behavior.

## Validate and hand off

- Validate parsing without starting a device or making a model request:

  ```sh
  python -c 'from pathlib import Path; from agentic_mobile_test.contracts import Scenario; Scenario.load(Path("tests/autotests/ui/android_settings/scenarios/<file>.json")); print("scenario valid")'
  ```

- Optionally verify pytest collects the scenario without executing it:

  ```sh
  pytest --collect-only -q tests/autotests/ui/android_settings/test_agentic_android_settings.py -k <scenario-id>
  ```

- Do not run pytest normally, start Appium, enable `--run-gemini`, alter billing, or change framework code as part of scenario authoring unless the user separately asks.
- Report the created file, assumptions, required interactions, and unsupported requirements that still need fixture or framework work. Point the user to `docs/workflow/README.md` for the later discovery and test-generation steps.
