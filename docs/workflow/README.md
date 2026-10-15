# One UI task: discover, generate, replay

Use a task whose expected behavior you understand. Gemini discovers how to
perform it through the current UI. Supply the expected result and what you know
about the starting state; discovery helps reveal the rest.

## 1. Start with one clear UI task

Write this short brief yourself or give it to your coding assistant:

```text
App suite: tests/autotests/ui/android_settings
Starting state: Android Settings is open at its root.
Task: Open About phone / About emulated device.
Expected result: Device name is visible.
Cleanup: Return to Settings root.
```

Keep the same suite path for subsequent tasks for that app.

You do not need to know every screen, locator or reusable fixture yet. Record
what you know and mark unknowns instead of inventing prerequisites. For a first
learning run, manual preparation is fine if you record it and have a safe way
to restore changed state. Do not prewrite the navigation for Gemini.

For example, a new task could be: “Open Unknown tracker alerts, enable alerts,
and run a manual scan.” Record the current alerts setting. If it is already on,
the run can explore scanning but cannot demonstrate enabling it. The expected
scan result must come from your known test environment, not Gemini's guess.
This is an example brief, not an already-supported runnable scenario.

The UI fixture defaults to opening and returning to Settings root. A scenario
can set `"start_screen": "home"` and `"cleanup_screen": "home"` instead (Android).
These are executable checkpoints, unlike descriptive preconditions. It does not restore
arbitrary settings. Record additional state before changing it and restore it
during teardown. The YouTube example has its own network preparation in test
code; new tasks do not automatically inherit it.

## 2. Save the task contract

Ask your coding assistant to translate that brief using
[scenario-template.json](scenario-template.json), or fill in the template yourself.
Save one task per JSON file under:

```text
tests/autotests/ui/<app_suite>/scenarios/<task_name>.json
```

For the existing Settings suite, use `android_settings/scenarios/`.
The existing discovery test collects each JSON directly in that folder; a new
task does not need a copy of the discovery test.

The contract supplies the goal, fixed text assertions, permitted actions,
test data and step limit. `scenario_type` remains required metadata in the
current schema; use the appropriate value for your task without generating
additional cases. `required_interactions` can require a particular tap or
text-entry action before success.

Before spending on discovery, check only what is needed to run it honestly:

- Known prerequisites are satisfied, manually or by existing setup. Record any
  manual preparation; JSON `preconditions` and `cleanup` do not execute it.
- Assertions prove the requested outcome. Current contract assertions check
  visible/absent text. Add `"checked": true` or `false` to verify the actual
  Android toggle state; the text must identify the switch or its immediate row
  label uniquely. Missing, unreadable or ambiguous controls cannot pass.
  An optional `resource_id` from observed UI XML can identify a unique switch,
  with `text` providing screen context. Do not guess the ID.
  Ordered intermediate states and general long-running waits still need support.
- You know how to restore state changed by the task, even if this first run
  needs manual restoration. Automated replay will need deterministic cleanup.

Missing verification or action support is a framework gap, not a reason to
invent more prompt details. Evidence from an incomplete exploration can still
help you understand the workflow, but it is not a verified regression test.

A new app can have its own suite folder and scenario files. Executing it also
requires an appropriate collector and fixtures; the current generator emits the
Settings fixture. The commands below apply to the implemented Settings suite.

For verification-only tasks, set `"allow_toggle_changes": false`. The policy
blocks interaction with observed checkable controls and their clickable rows.
A uniquely identified toggle in the wrong state ends verification as a failure;
Gemini must not enable it to make the test pass. This guard relies on Android's
UI hierarchy, not a guarantee against every possible app-specific state change.

The [helper scenario](../../tests/autotests/ui/android_settings/scenarios/artemis_accessibility_helper_enabled.json)
implements Home → Settings → Accessibility → inspect Artemis Accessibility Helper
→ Home. Its assertion matches the helper name in a switch label/row; confirm
that label in the first device run. No locator or navigation sequence is assumed.
Use filename stem `artemis_accessibility_helper_enabled` and scenario ID
`artemis-accessibility-helper-enabled` in the commands below.

## 3. Prepare the session and select one task

Complete [first-time setup](../prerequisites.md) once, then start your emulator.

```sh
cd /Users/andrewsekar/repos/agentic-mobile-test
source .venv/bin/activate
adb devices
DEVICE_UDID='emulator-5554'

set -a
source .env
set +a
test -n "$GEMINI_API_KEY" && echo "Gemini key loaded"
```

Use the serial reported by `adb devices`. If `.env` is missing, create it with
`test -f .env || cp .env.example .env`, fill in your key, then load it again.
An already exported `GEMINI_API_KEY` also works.

Pytest starts Appium at `http://127.0.0.1:4725` when needed and stops the server
it started. For manual logs, run `npm run appium:start` from this repository in
a second terminal. If `curl -fsS http://127.0.0.1:4725/status` succeeds, reuse
that server.

The following values select the existing About phone task. For a new task,
replace them with its JSON filename (without extension) and `scenario_id`:

```sh
SCENARIO_STEM='android_settings_about_phone'
SCENARIO_ID='android-settings-about-phone'
SCENARIO_FILE="tests/autotests/ui/android_settings/scenarios/${SCENARIO_STEM}.json"
DISCOVERY_TEST="tests/autotests/ui/android_settings/test_agentic_android_settings.py::test_agentic_android_settings_scenario[${SCENARIO_ID}]"

python -c 'import sys; from pathlib import Path; from agentic_mobile_test.contracts import Scenario; Scenario.load(Path(sys.argv[1])); print("Task contract valid")' "$SCENARIO_FILE"
pytest --collect-only -q "$DISCOVERY_TEST"
```

Expect one collected test. Neither validation command calls Gemini.

## 4. Let Gemini discover the path

```sh
pytest "$DISCOVERY_TEST" \
  --run-gemini \
  --appium-udid "$DEVICE_UDID" \
  --appium-package com.android.settings --appium-activity .Settings \
  --appium-no-reset -q
```

Gemini receives the goal, screenshot and current UI elements, selects one
permitted action, and observes the result after Appium executes it.
Before each observation, the observer polls every 0.2 seconds and requires
unchanged screenshot bytes, UI hierarchy, and app/activity for at least 0.6
seconds. Polling times out after 10 seconds (individual Appium commands retain
their own transport timeouts). Only the accepted capture goes to Gemini and
the discovery path; intermediate captures remain local diagnostics.
This conservative check can time out on continuous animation, video, or a
spinner. It reports a synchronization failure rather than silently sending an
unstable frame. It does not replace a test-specific wait for a business result.
The current discovery test allows up to `max_steps` action requests, 100 output
tokens per action and $0.005 estimated cost per run, with SDK retries disabled.
These are local request limits, not a provider billing cap.

## 5. Review the discovery record

```sh
find runs -name result.json -print
```

Identify the new attempt for your task. Set the directory directly containing
its `result.json` and successful `discovered-path.json`:

```sh
RUN_DIR='runs/replace-with-fixture-directory/replace-with-agent-run-directory'
```

The actual output name is **`discovered-path.json`** within a unique run
directory. Review it alongside `scenario.json`, `steps.jsonl`, screenshots,
UI XML, and `lifecycle.json`. Check any task-specific setup/cleanup records in
the parent directory too.

Require the whole pytest test to pass, including cleanup. The loop can write a
successful discovery record before later test assertions or teardown fail.
A failed loop retains diagnostic records but produces no successful path;
resolve the cause before generating a regression.

Now decide what belongs in the repeatable test from the observed journey:

- **Setup:** state that must already hold before the behavior under test.
- **Test actions:** the behavior you actually want to exercise.
- **Assertions:** observable proof of the expected result.
- **Cleanup:** restoring state, including after a failure.

For “enable alerts and scan,” alerts off is the starting condition; enabling
them belongs in the test. For “scan with alerts enabled,” alerts on can be setup.
The same discovered action can have a different role depending on the task.
Gemini's action trace does not classify these roles for you.

Make necessary preparation repeatable before validating replay. Start with
task-specific setup; share a fixture when another test needs the same state.
Keep reusable device operations under `src/agentic_mobile_test/`. If discovery
reveals that you started from the wrong state, correct it and rediscover rather
than treating the old path as proof of the intended behavior.

## 6. Generate a replay candidate from that record

Review the recorded tap/type targets and scroll destinations against
[the target catalog](../../tests/autotests/ui/android_settings/targets/android_settings.json).
Your coding assistant can use the actual UI XML to add missing stable targets.
You do not need to prewrite the navigation locators for discovery.

When a recorded locator does not match exactly one catalog target, create a
reviewed `target-map.json` in the run directory:

```json
{
  "schema_version": 1,
  "step_targets": {
    "2": "settings.about_device"
  }
}
```

Replace the example with actual discovery step numbers and existing catalog IDs.
Scroll steps also need a destination; the generator uses a subsequent mapped
target when possible.

```sh
CANDIDATE="tests/autotests/ui/android_settings/test_${SCENARIO_STEM}.py.candidate"

python -m agentic_mobile_test.generation "$RUN_DIR" \
  --scenario "$SCENARIO_FILE" \
  --target-catalog tests/autotests/ui/android_settings/targets/android_settings.json \
  --output "$CANDIDATE"
```

If you created a map, append `--target-map "$RUN_DIR/target-map.json"` to that
command. Keep the original scenario unchanged. Generation checks recorded
assertions, selected contract fields, evidence hashes and target mappings; it
renders Python without calling Gemini. Existing candidates are not overwritten.

## 7. Review and validate the generated replay

Open the `.py.candidate`. Confirm it performs the observed actions and has
the necessary setup, assertions, waits and cleanup. In particular:

- Generation includes the Settings suite fixture, which honors the scenario's
  start/cleanup screen checkpoints. Add any other
  task-specific fixture support used during discovery; it is not copied automatically.
- Final text verification reads one observation. Add bounded waits for
  asynchronous results where needed.
- Manually compare required interactions and test-data values with the approved
  task; the current recorded contract does not freeze those fields fully.

After review, remove only the `.candidate` suffix, keeping the file beside the
other Python tests so its relative scenario path remains valid:

```sh
TEST_FILE="${CANDIDATE%.candidate}"
if test -e "$TEST_FILE"; then
  echo "Test exists; review it before replacing: $TEST_FILE"
else
  mv "$CANDIDATE" "$TEST_FILE"
fi
```

If a test already existed, resolve that review before continuing. Run the
reviewed generated test:

```sh
pytest "$TEST_FILE" \
  --appium-udid "$DEVICE_UDID" \
  --appium-package com.android.settings --appium-activity .Settings \
  --appium-no-reset -q
```

This run uses Appium without Gemini. A passing replay with verified assertions
and cleanup completes the experiment. Preserve the reviewed test, task contract,
targets and fixtures together; keep generated evidence and keys local.

Clear the key at session end when finished: `unset GEMINI_API_KEY`.
