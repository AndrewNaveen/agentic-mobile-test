# Agentic Mobile Test

An experimental Python/pytest framework for discovering mobile UI workflows
with an LLM, executing approved actions through Appium, and turning reviewed
discoveries into deterministic regression tests. The model proposes actions;
the framework enforces the action policy and deterministic assertions decide
the result. The framework owns its discovery, execution, and evidence workflow.

## First-time setup

Complete the machine and account setup in [Prerequisites](docs/prerequisites.md)
once. It covers Python, Android Studio/emulator, project-local Appium, and the
optional Gemini API key. Do all repository commands from the project root:

```sh
cd /Users/andrewsekar/repos/agentic-mobile-test
```

Before the first Gemini run, create the local key file if it does not exist:

```sh
test -f .env || cp .env.example .env
```

Edit `.env` and set `GEMINI_API_KEY` to your key. This file is ignored by Git.
On macOS, `open -e .env` opens it in TextEdit. Do this once; do not repeat it
at the start of each session.

## Every work session

1. Start the Android emulator in Android Studio.
2. In a terminal, enter the repository and activate Python:

   ```sh
   cd /Users/andrewsekar/repos/agentic-mobile-test
   source .venv/bin/activate
   adb devices
   ```

3. For a Gemini discovery run, load the key from the ignored project-root
   `.env` file without printing it. The file must first be created and filled
   in using the one-time setup above:

   ```sh
   set -a
   source .env
   set +a
   test -n "$GEMINI_API_KEY" && echo "Gemini key loaded"
   ```

4. Appium is normally started by pytest on this project's dedicated port 4725.
   If you want to start it yourself to see server logs, first check whether
   that port is already serving Appium:

   ```sh
   curl -fsS http://127.0.0.1:4725/status
   ```

   If it is not already running, start it from the repository root:

   ```sh
   npm run appium:start
   ```

   Keep it running. Open a second terminal, repeat steps 2–3, then run pytest.
   If the status check succeeds, do not start another server; pytest will reuse
   the one already listening on `127.0.0.1:4725`.

## Run the YouTube discovery

With the emulator connected and the Gemini key loaded in the pytest terminal:

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

Change `emulator-5554` to the serial shown by `adb devices`. This scenario
captures and restores the original network state, turns on Airplane mode,
launches YouTube, and verifies its offline screen. Gemini makes paid API calls
within the scenario's configured limits. For the full authoring, evidence review,
and deterministic-test workflow, see [Working with the project](docs/workflow/README.md).

## Run without an LLM

The Android Settings baseline and unit suite do not call Gemini:

```sh
source .venv/bin/activate
pytest
```

The deterministic YouTube replay is a separate test:

```sh
pytest tests/autotests/ui/android_settings/test_youtube_airplane_mode_offline.py \
  -m appium --appium-udid emulator-5554 \
  --appium-package com.android.settings --appium-activity .Settings \
  --appium-no-reset -q
```

## Project map

- `src/agentic_mobile_test/` — agent loop, Appium/device adapters, Gemini
  gateway, verification, evidence, and test generation.
- `tests/unit/` — offline tests; `tests/integration/` — opt-in provider tests;
  `tests/autotests/ui/` — live mobile scenarios and pytest fixtures.
- `docs/workflow/README.md` — scenario-to-discovery-to-regression instructions.
- `runs/` — local screenshots, UI snapshots, logs, and run records; ignored by Git.
