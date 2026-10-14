# Working with Agentic Mobile Test

This is the day-to-day guide for preparing a scenario, running Appium and Gemini discovery, reviewing the recorded path, and generating a deterministic pytest candidate. Start here when you return to the project.

## The workflow at a glance

```text
Write a reviewed scenario JSON
        ↓
Start emulator; load Gemini key
        ↓
Run one pytest scenario (pytest starts local Appium if needed)
        ↓
Review screenshots, UI snapshots, actions, and fixed assertions
        ↓
Generate a .py.candidate from a passed discovery
        ↓
Review, promote, and run it as deterministic regression
```

The model only proposes one action per observation. Policy checks it, Appium executes it, and deterministic assertions decide whether discovery passed. Do not treat model output or a screenshot as the test verdict.

## 1. One-time setup

Set up Python, Android Studio/SDK, the emulator, project-local Appium, and the
optional Gemini key by following [First-Time Prerequisites](../prerequisites.md).
Do not repeat `npm ci` or `npm run appium:setup` every session. Always run
project commands from the repository root; otherwise npm cannot find this
project's `package.json` and lockfile.

## 2. Describe a scenario

There is not yet an interactive natural-language scenario command. Copy [scenario-template.json](scenario-template.json), fill it in, and save it as a JSON file in:

```text
tests/autotests/ui/android_settings/scenarios/<scenario-name>.json
```

You can ask a coding agent to draft and validate this file instead of writing
the JSON yourself. This repository includes the [author-mobile-scenario
skill](../../.agents/skills/author-mobile-scenario/SKILL.md). In Codex, invoke
it with `$author-mobile-scenario`, then describe the scenario in plain English.
In another Agent Skills-compatible agent, use that agent's skill interface or
ask it explicitly: “Read `.agents/skills/author-mobile-scenario/SKILL.md` and
follow it to draft a scenario for: …”. Some agents require a different
discovery directory for automatic slash-command invocation; the SKILL.md
instructions themselves are portable, but installation paths and commands are
host-specific.

The shared test automatically loads every JSON file in that folder. Use this shape:

```json
{
  "schema_version": 1,
  "scenario_id": "youtube-airplane-mode-offline",
  "scenario_type": "edge",
  "goal": "Turn on Airplane mode in Settings, launch YouTube, dismiss its notification prompt if shown, and verify its offline screen.",
  "preconditions": [
    "Android Settings is open at its root screen",
    "Airplane mode is off",
    "YouTube is installed"
  ],
  "cleanup": [
    "Restore the device network state captured before the scenario"
  ],
  "assertions": [
    {
      "assertion_id": "offline-message",
      "text": "Connect to the internet",
      "exact": false,
      "expectation": "visible"
    }
  ],
  "allowed_actions": [
    "tap",
    "scroll_forward",
    "press_back",
    "launch_app"
  ],
  "required_interactions": [
    {
      "action": "tap",
      "target_text": "Airplane mode",
      "minimum_count": 1
    }
  ],
  "test_data": {},
  "launchable_apps": {
    "youtube": "com.google.android.youtube"
  },
  "max_steps": 10
}
```

The YouTube offline scenario stops at the offline state; the loading spinner and
offline message are sufficient for that check. Retry is a separate deterministic
test because its control appears later. That test uses the shared
`device.actions.wait_until_visible` and `wait_until_clickable` methods before
tapping it. Run it without Gemini:

```sh
pytest tests/autotests/ui/android_settings/test_android_settings.py::test_youtube_offline_retry_waits_until_actionable \
  -m appium --appium-udid emulator-5554 \
  --appium-package com.android.settings --appium-activity .Settings \
  --appium-no-reset -q
```

Current scenario rules:

- `scenario_id` becomes the pytest parameter ID; keep it unique and descriptive.
- Use `positive` when the requested behavior should succeed, `negative` when a controlled invalid/unavailable condition should be rejected, and `edge` for a boundary or recovery case. The engineer defines what correct behavior means; Gemini explores the UI path, not product requirements.
- `goal` tells Gemini what to accomplish. `preconditions` and `cleanup` are descriptive; add matching deterministic setup/teardown when a test depends on them.
- `required_interactions` prevents visible final text from ending a run too early. A required tap is counted only after the policy accepts an enabled, clickable target and Appium executes it. Use it for required taps or text entry; it is not a general ordered-checkpoint language. Essential device-state changes and app launches also need deterministic fixture checks or independent assertions.
- `allowed_actions` is the safety allowlist: `tap`, `type_text`, `launch_app`, `scroll_forward`, `scroll_backward`, `press_back`.
- For `launch_app`, list approved aliases and app IDs in `launchable_apps`. The planner returns an alias such as `youtube`, never an arbitrary package ID. A missing installed app fails at launch.
- `test_data` contains named values that can be referenced by `type_text`; avoid putting secrets in scenario JSON or evidence.
- Assertions currently check visible or absent text. `exact: false` means the expected phrase may be part of a longer UI string.
- `max_steps` bounds model actions (1–50). Set it as low as is reasonable; each step can make a paid model call.

Keep cross-app/device capabilities in `src/agentic_mobile_test/device/`. Keep app-specific scenarios, locators, and UI setup in that app's test feature folder. A new scenario should use existing capabilities where possible; only add shared code when the capability genuinely generalizes.

### YouTube Airplane-mode scenario setup

The agentic YouTube test captures and restores the original radio state, starts with mobile data enabled and Wi-Fi/Airplane mode disabled, and checks YouTube is installed before making a paid model call. Appium's reported mobile-data bit can remain set while Airplane mode is on; the offline screen is the application-level oracle. The separate Retry test waits up to 60 seconds for YouTube to expose Retry, then waits for it to be clickable before tapping.

## 3. Start each work session

Start the emulator in Android Studio. In your pytest terminal, enter the
repository, activate the virtual environment, and confirm the device:

```sh
cd /Users/andrewsekar/repos/agentic-mobile-test
source .venv/bin/activate
adb devices
```

For Gemini discovery, load the key in this same terminal from the ignored
project-root `.env` file. This does not display the key:

```sh
set -a
source .env
set +a
test -n "$GEMINI_API_KEY" && echo "Gemini key loaded"
```

### Appium server: choose one method

**Normal run:** do not start Appium separately. Pytest starts the project-local
server at `http://127.0.0.1:4725` and stops it when the test finishes.

**Manual server:** to see Appium logs, first check whether the default port is
already serving Appium:

```sh
curl -fsS http://127.0.0.1:4725/status
```

If it is not ready, open another terminal and run this from the repository
root:

```sh
cd /Users/andrewsekar/repos/agentic-mobile-test
npm run appium:start
```

Leave that terminal open. Run pytest in the first terminal; it reuses the
server on port `4725`. If the status check already succeeded, do not start a
second server on the same port. The key is needed only in the pytest terminal,
not in the Appium terminal. `npm run appium:start` from `~` fails because npm
cannot find the repository's `package.json` there.

## 4. Run discovery

First, check the Appium path without spending on Gemini:

```sh
pytest -m appium \
  --appium-udid emulator-5554 \
  --appium-package com.android.settings \
  --appium-activity .Settings \
  --appium-no-reset -q
```

Then run only the scenario whose ID you added (the ID is matched by `-k`):

```sh
pytest tests/autotests/ui/android_settings/test_agentic_android_settings.py \
  -m "appium and gemini" \
  -k youtube-airplane-mode-offline \
  --run-gemini \
  --appium-udid emulator-5554 \
  --appium-package com.android.settings \
  --appium-activity .Settings \
  --appium-no-reset -q
```

Replace the UDID with the value from `adb devices`. The test and manual server
use port `4725` by default. Gemini tests are skipped unless `--run-gemini` is
present. The live test limits calls to its scenario step budget, output to 100
tokens per call, and estimated run cost to `$0.005`; automatic retries are
disabled.

## 5. Review discovery evidence

Each run writes under `runs/` (ignored by Git). Find discovery records with:

```sh
find runs -name discovered-path.json -print
```

Open the `discovered-path.json` belonging to the matching scenario. Review its sibling `scenario.json`, `steps.jsonl`, `result.json`, screenshots, and UI XML snapshots. Check every action and transition. A passed discovery is evidence for review—not yet an approved regression.

## 6. Generate and promote a regression candidate

Use the run directory that directly contains `discovered-path.json` and the exact scenario JSON used for that run:

```sh
python -m agentic_mobile_test.generation \
  runs/<run-directory> \
  --scenario tests/autotests/ui/android_settings/scenarios/youtube_airplane_mode_offline.json
```

If a discovered tap target does not uniquely match the reviewed catalog at `tests/autotests/ui/android_settings/targets/android_settings.json`, create a target-map JSON and pass `--target-map path/to/map.json`. Target maps convert discovery step numbers to stable catalog target IDs; review those mappings yourself.

The generator checks that discovery passed, its assertions and scenario still match, evidence hashes are intact, and actions/targets are approved. It writes a `.py.candidate` beside the scenario; pytest does not collect that suffix. Review the generated code, assertions, setup, and cleanup. Only after review, copy/rename it to `.py`, run that test on the emulator, and inspect its evidence. Do not promote a candidate just because generation succeeded.

## What is and is not automatic

Automatic today: scenario collection, Appium session/server lifecycle, Settings-root fixture setup/teardown, the YouTube discovery scenario's network precondition and radio-state restoration, action-policy checks, Gemini action selection, Appium execution, evidence capture, deterministic text verification, reusable bounded UI waits, and review-only candidate generation.

Still engineer-owned: ensuring the emulator has working mobile-data internet, choosing trustworthy pass/fail oracles, reviewing locators and generated code, and deciding whether a discovered path is a suitable regression. The project does not yet accept a plain-English scenario directly from the terminal or automatically author and approve durable tests.

## Session close

After paid model experimentation, review usage and clear the key from this shell:

```sh
unset GEMINI_API_KEY
```

Keep run artifacts local. Never commit API keys, generated evidence, or unreviewed candidate files.
