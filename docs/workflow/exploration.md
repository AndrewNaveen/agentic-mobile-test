# Explore before defining tests

This separate mode investigates a UI without success assertions. The existing
scenario runner and deterministic replay workflow are unchanged.

## 1. Prepare an isolated environment

Log in manually with Gemini stopped. Use demo devices and test data only.
Open the starting page. Record any device state you may need to restore.
The Appium session launches the configured app; check that it preserves your
intended starting page. Starting-state prose is context, not an executable check.

## 2. Save a brief

For example, save this as `home-assistant-exploration.json` outside the
existing scenario directories (this is NOT a scenario JSON):

```json
{
  "objective": "Explore Overview and demo media-player navigation. Identify reachable controls and backtrack to investigate different branches. Do not deliberately change playback or volume yet.",
  "app_package": "io.homeassistant.companion.android",
  "starting_state": "Logged in on Overview; Welcome Andrew is visible",
  "boundaries": [
    "Use only the isolated demo server",
    "Do not change account or server settings, delete anything, or operate real devices",
    "Request guidance if a control's effect is unclear"
  ],
  "cleanup": "Manually return to Overview and restore any changed demo state",
  "sandbox_confirmed": true,
  "max_steps": 10,
  "allow_toggle_changes": false
}
```

No locators, expected results, or required tap sequence are needed. `max_steps`
bounds model decisions, including stop decisions. Gemini's existing call/token/
estimated-cost limits still apply; reaching them can stop exploration earlier.

## 3. Run through pytest

Use the normal virtual environment, Appium prerequisites and Gemini key setup.
Find the installed app's launch activity rather than guessing it:

```sh
adb -s emulator-5554 shell cmd package resolve-activity --brief io.homeassistant.companion.android
```

Substitute the returned activity (the part after `/`) below:

```sh
pytest tests/autotests/ui/exploration/test_exploratory_app.py \
  --run-gemini \
  --exploration-brief /absolute/path/home-assistant-exploration.json \
  --appium-udid emulator-5554 \
  --appium-package io.homeassistant.companion.android \
  --appium-activity '<resolved activity>' \
  --appium-no-reset -q
```

This command makes paid model calls. Nothing runs merely by saving the brief.
The entry point does not use the Android Settings lifecycle fixture.

## 4. Review the report and perform cleanup

The terminal prints the exact `runs/.../exploration.json` path. The report contains:

- Observed screens, element refs, labels and available control attributes.
- Copied screenshots and UI sources with hashes.
- Proposed actions, execution results and before/after screen references.
- Partial attempts when execution or observation fails.
- Stop reason: completed, needs_guidance, budget_exhausted, blocked or error.

`completed` means the model chose to stop, not that it covered every screen or
verified the app. A passing pytest entry point means the exploration harness
finished normally, not that a product test passed. No `discovered-path.json` is
produced and this report must not be fed directly to the regression generator.

Cleanup is manual in this first mode; its report status remains unverified.
Review navigation helpers, fixtures and test candidates afterward with your
coding assistant. Automated generation from these reports is a later step.

## Safety limits and known gaps

The policy enforces action types, current target references, safe locators,
step limits, repeated ineffective actions and detected toggle restrictions.
The runner checks the observed foreground package before model calls and after
actions. It stops on an unexpected package; it cannot prevent a tap from opening
one, nor undo that action. Generic taps can mutate state even when a control is
not labeled as a toggle. Natural-language boundaries guide Gemini but are NOT
an enforceable read-only guarantee. Use an isolated sandbox.

Screen observations, text and screenshots may contain sensitive information;
screenshots and navigation history are sent to Gemini. Do not explore login,
payment or personal-data screens. Reports are not automatically redacted.

Branching is model-directed through bounded history and back actions, not an
exhaustive crawler. There is no guaranteed return to the initial screen. This
first implementation has offline coverage only; Home Assistant controls and
WebView accessibility still need live validation. Existing audit findings,
including target changes between observation and execution, remain open.
