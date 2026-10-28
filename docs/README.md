# Start here — exploration workflow

Explore an isolated Android app with Gemini and Appium, review the saved evidence,
then use a coding assistant to write deterministic pytest tests.

**Start at step 1 and follow this page through to the results.**
Open terminals → prepare app → create brief → run exploration → review results.

The copyable examples use Home Assistant. For a different app, open the
"Another app" sections in steps 3, 5 and 6.

For a new machine or checkout, complete [first-time installation](setup/installation.md),
then return to step 1. On later sessions, start directly below.
Commands use macOS, `$HOME/repos/agentic-mobile-test` and the `Pixel_10_Pro` AVD;
substitute your checkout path or AVD name if different.

## 1. T1 — Open your working terminal

**Gemini API key:** [create the local `.env` key file](setup/installation.md#create-a-gemini-key-file)
once. The commands below export its values so Python can read them in this terminal.

Open a terminal tab, called **T1** in this guide:

```sh
cd "$HOME/repos/agentic-mobile-test"
source .venv/bin/activate
export ANDROID_HOME="$HOME/Library/Android/sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
set -a
source .env
set +a
```

This activates your existing virtual environment and loads your Gemini key.
Keep T1 open: app setup, brief editing and pytest all happen here.

## 2. T2 — Start Android

Open a second terminal tab, **T2**:

```sh
cd "$HOME/repos/agentic-mobile-test"
"$HOME/Library/Android/sdk/emulator/emulator" -avd Pixel_10_Pro -port 5554
```

Leave T2 running. Wait for Android to boot and unlock the screen. This emulator's
serial is `emulator-5554`. If the emulator is already running, reuse it.

## 3. T1 — Prepare and select your app

Choose your app, prepare its starting screen and note its original state for cleanup.

### Home Assistant

Follow [Home Assistant setup](app/homeassistant/setup.md) to start its demo
server and sign in on the emulator. Then continue to step 4. The commands below
already contain Home Assistant's package, activity and brief paths.

<details>
<summary>Another app — prepare it</summary>

Install the app on the emulator, start its server if needed and sign in with an
isolated demo account. Note its Android package name. To find its launch activity,
replace `YOUR_APP_PACKAGE` below with that package:

```sh
adb -s emulator-5554 shell cmd package resolve-activity --brief YOUR_APP_PACKAGE
```

The result contains `package/activity`. Use the part after `/` for the activity
in step 6. Continue to step 4.

</details>

## 4. T3 — Start Appium

Open a third terminal tab, **T3**:

```sh
cd "$HOME/repos/agentic-mobile-test"
npm run appium:start
```

Leave T3 running. Reuse your project server if it is already running on port 4725.
Back in **T1**, check readiness once:

```sh
adb devices
curl -fsS --max-time 5 http://127.0.0.1:4725/status
```

Expect `emulator-5554` listed as `device` and Appium JSON with `value.ready: true`.
For startup problems, see [Appium troubleshooting](setup/appium.md#troubleshooting).
**Continue in T1 for all remaining steps.**

## 5. T1 — Create and edit your brief

A brief is the JSON file containing your exploration instructions. Choose the
commands for your app below. They create a working copy and open it for editing;
an existing copy is kept.

### Home Assistant brief

```sh
mkdir -p runs/app/home-assistant
test -f runs/app/home-assistant/brief.json || cp docs/app/homeassistant/media-player.json runs/app/home-assistant/brief.json
open -e runs/app/home-assistant/brief.json
```

**Edit and save `runs/app/home-assistant/brief.json`.** The template already
contains the app identifiers and an objective for one demo player's play/pause
controls. Review and edit it for your investigation.

<details>
<summary>Home Assistant — explore sliders instead</summary>

Create a separate brief for slider experiments:

```sh
mkdir -p runs/app/home-assistant
test -f runs/app/home-assistant/sliders.json || cp docs/app/homeassistant/sliders.json runs/app/home-assistant/sliders.json
open -e runs/app/home-assistant/sliders.json
```

**Edit and save `runs/app/home-assistant/sliders.json`.** This template permits
short slider drags and records their visible effects. Review its objective and
cleanup instructions, then confirm isolation as described below. Use the slider
command in step 6.

</details>

<details>
<summary>Another app — create its brief</summary>

Replace `demo-app` in the paths with your app's name:

```sh
mkdir -p runs/app/demo-app
test -f runs/app/demo-app/brief.json || cp docs/exploration/brief-template.json runs/app/demo-app/brief.json
open -e runs/app/demo-app/brief.json
```

**Edit and save `runs/app/demo-app/brief.json`:** set `app_slug`, `app_package`
and `objective` for your app.

</details>

### Before saving your brief

1. Name the investigation with `investigation_slug`.
2. Review `objective`, `boundaries`, `cleanup` and `max_steps`. Enable `allow_toggle_changes` only if your objective permits toggle controls.
3. Confirm the selected account, server and devices are isolated and safe to modify, then set `sandbox_confirmed` to `true` and save.

[Brief field details](exploration/briefs.md#brief-fields) explain the available settings.
**Continue to step 6 after saving.**

## 6. T1 — Run exploration

`--exploration-brief` takes **the path to the JSON file you saved in step 5**.
The command reads that file; it does not create it.

`--run-gemini` opts into paid model requests and uploading UI evidence. The
explorer can change app state within its permitted actions.

### Run Home Assistant

```sh
python -m pytest tests/autotests/ui/exploration/test_exploratory_app.py \
  --run-gemini \
  --exploration-brief runs/app/home-assistant/brief.json \
  --appium-server-url http://127.0.0.1:4725 \
  --appium-udid emulator-5554 \
  --appium-package io.homeassistant.companion.android \
  --appium-activity .launch.LaunchActivity \
  --appium-no-reset -q
```

<details>
<summary>Home Assistant — run the slider brief</summary>

Use the slider brief saved in step 5:

```sh
python -m pytest tests/autotests/ui/exploration/test_exploratory_app.py \
  --run-gemini \
  --exploration-brief runs/app/home-assistant/sliders.json \
  --appium-server-url http://127.0.0.1:4725 \
  --appium-udid emulator-5554 \
  --appium-package io.homeassistant.companion.android \
  --appium-activity .launch.LaunchActivity \
  --appium-no-reset -q
```

</details>

<details>
<summary>Another app — run exploration</summary>

Use the same brief path you edited in step 5. Replace `YOUR_APP_PACKAGE` and
`YOUR_LAUNCH_ACTIVITY` with your app's values from step 3:

```sh
python -m pytest tests/autotests/ui/exploration/test_exploratory_app.py \
  --run-gemini \
  --exploration-brief runs/app/demo-app/brief.json \
  --appium-server-url http://127.0.0.1:4725 \
  --appium-udid emulator-5554 \
  --appium-package YOUR_APP_PACKAGE \
  --appium-activity YOUR_LAUNCH_ACTIVITY \
  --appium-no-reset -q
```

</details>

Use your device's serial if different. `--appium-no-reset` preserves login/data
and is required by this runner; Appium may relaunch the app. Run one exploration
at a time. Budget details are in the [model gateway reference](reference/model-gateway.md).
**When pytest finishes, continue to step 7.**

## 7. Read the results

Pytest prints the absolute path to `exploration.json`. Open **`report.md` in that
same folder** first: it contains findings, evidence and unresolved questions.
Each execution saves a new folder under
`runs/apps/<app_slug>/<investigation_slug>/<run-id>/`.

- **`completed`** means the model's final review accepted the investigation evidence. Review it before deciding what to test.
- **`blocked`, `needs_guidance`, `budget_exhausted`, `review_unavailable`** mean a partial investigation; pytest skips and records the reason.
- **`error`** means an execution error; pytest fails. Inspect the saved attempts and evidence.

Restore the original app state using your brief's `cleanup` instructions.
For individual output files, see [Working briefs and results](../runs/README.md).

For another objective, create a different brief file in step 5 and give it a new
`investigation_slug`. Prepare its starting screen, then run step 6 with
`--exploration-brief` pointing to that new file.
To turn the findings into a test, continue below.

## 8. Author a deterministic test

**Next, give the run folder to your coding assistant.** It contains the report,
action trail and screenshot/XML evidence needed to draft a test.

For the Home Assistant playback run, paste this request into your coding assistant:

```text
Review this exploration and prepare the smallest deterministic pytest candidate:
runs/apps/home-assistant/playback-controls/2026-10-21T205456.159567Z-100fa8db/

Verify the recorded evidence hashes. Compare the report's claims with the
screenshots, XML and executed actions. State exactly which transition was
observed, what remains unproven, and which expected behavior needs my approval.

Use the existing AppiumActions operations. Keep app selectors and helpers local
to tests/autotests/ui/homeassistant/. Keep setup and cleanup in local fixtures;
setup must not exercise the behavior under test. The candidate must not require
Gemini or the exploration report at runtime.

Prepare the candidate and its explicit replay command for review. Do not change
the low-level action contracts or run a new paid exploration.
```

For a different run, replace the run folder and app test folder in that request.

Review the proposed assertion against your requirements, then replay the test on
the demo device. A model's review does not approve the expected behavior. Keep
the test as a candidate until the expectation is approved and a real Appium replay
has verified it. Replay uses pytest with device/app arguments, without
`--run-gemini` or `--exploration-brief`.

[Test authoring details](exploration/test-authoring.md) explain evidence review,
fixtures and when to extract reusable functions. Test authoring is currently
coding-assisted; no automatic test generator is active.

## 9. T1 — Replay the authored test

The first Home Assistant candidate is now
[test_playback.py](../tests/autotests/ui/homeassistant/test_playback.py).
It checks **Pause → Play** on the isolated Living Room demo player.

Prepare the demo app using steps 1–4. Leave Overview visible with Living Room
playing. In T1, run:

```sh
python -m pytest tests/autotests/ui/homeassistant/test_playback.py \
  --appium-server-url http://127.0.0.1:4725 \
  --appium-udid emulator-5554 \
  --appium-package io.homeassistant.companion.android \
  --appium-activity .launch.LaunchActivity \
  --appium-no-reset -q
```

This test runs without Gemini, a brief or the originating exploration report.
Setup verifies the playing precondition and opens the player. The test taps Pause
and requires Play to appear. Cleanup resumes the player and returns to Overview,
checking the restored playing indicator.

Pytest prints **Replay evidence:** followed by the folder containing before/after
screenshots and XML. A passing replay reports `1 passed`; setup and cleanup
failures are reported separately. Inspect failure evidence before changing the
candidate; keep the expected behavior explicit.

## Finish your session

After restoring app state, press **Ctrl+C** in T3 to stop Appium and close the
emulator window. For Home Assistant, optionally
[stop the demo server](app/homeassistant/setup.md#stop-the-demo-server) in T1.
Then close your terminals.

## Technical details

- [Explorer architecture and flowcharts](reference/architecture/explorer.md)
- [Appium actions](reference/appium-actions.md)
- [Model gateway and budgets](reference/model-gateway.md)
