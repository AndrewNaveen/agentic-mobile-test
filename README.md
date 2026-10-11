# Agentic Mobile Test

This learning project implements a small, inspectable agentic mobile-testing
loop. An LLM may choose the next semantic action from the current screenshot
and Android UI hierarchy, but deterministic code validates and executes every
action through Appium. The LLM never controls the final verdict.

Artemis is useful reference material, but it is not a dependency or execution
path in this repository.

## What the project demonstrates

```text
approved scenario
      ↓
Appium observation (screenshot + UI hierarchy)
      ↓
structured LLM action using an observed element reference
      ↓
deterministic policy validation
      ↓
AppiumActions execution
      ↓
new observation + independent assertion
      ↓
evidence-backed result
```

The current code includes the contracts, provider-neutral planner boundary,
action policy, Appium observation and execution adapters, independent visible-
text verifier, bounded loop, local evidence writer, a semantic-target resolver,
and a cross-platform device facade. The opt-in Gemini gateway is cost-bounded
and kept separate from normal offline pytest runs.

## Setup

Python 3.11 or later, Node.js, Android Studio, an Android emulator, and the
Android platform tools are required. See [prerequisites](docs/prerequisites.md).

Create the Python environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,appium]'
```

Install the project-local Appium server and UiAutomator2 driver:

```sh
npm ci
npm run appium:setup
npm run appium:doctor
```

Run the deterministic architecture checks:

```sh
source .venv/bin/activate
pytest
```

These checks use fakes for the model and Appium execution. They prove contract,
policy, orchestration, evidence, and failure behavior; they do not claim that a
real device journey works yet.

## Run the Android Settings baseline

The first live test opens Android Settings, scrolls to **About phone** (called
**About emulated device** on recent Android emulators), taps it, and verifies
that **Device name** is visible. This is intentionally a scripted Appium
baseline; it proves the runner, action layer, device connection, and oracle
before an LLM replaces the target-selection step.

Start an English-language emulator and confirm its serial with `adb devices`,
then run:

```sh
pytest -m appium \
  --appium-udid emulator-5554 \
  --appium-package com.android.settings \
  --appium-activity .Settings \
  --appium-no-reset
```

Pytest starts the project-local Appium server, creates a new WebDriver session,
and writes screenshots plus UI-source evidence beneath `runs/`. If Appium is
already running at `127.0.0.1:4723`, pytest reuses it.

The baseline uses durable target names from
`tests/autotests/ui/targets/android_settings.json`. The resolver checks locator
candidates in reviewed order, requires exactly one eligible match, and writes
`locator-trace.jsonl` in the run directory. A trace identifies the catalog,
screen, locator attempts, match counts, selected rank, current activity, and
failure evidence.

For a future APK-based scenario, use:

```sh
pytest -m appium \
  --appium-udid emulator-5554 \
  --appium-app /absolute/path/to/application.apk
```

The model provider remains unselected. The baseline does not make a network or
LLM call.

## Structure

```text
src/agentic_mobile_test/
├── contracts.py          # Scenario, observation, action, trace, and verdict types
├── planner.py            # Strict structured-output LLM boundary
├── policy.py             # Deterministic action and repetition guardrails
├── runner.py             # Bounded observe-plan-act-verify loop
├── verifier.py           # Independent deterministic assertions
├── artifacts.py          # Redacted scenario, step, and result evidence
├── device/
│   ├── profile.py        # Session identity and live screen geometry
│   ├── platform.py       # Android/iOS operating-system adapters
│   └── facade.py         # MobileDevice, system settings, and semantic UI
└── appium/
    ├── actions.py        # Reviewed deterministic Appium operations
    ├── models.py         # Low-level action data types
    ├── observer.py       # Screenshot/UI-tree perception and element references
    ├── executor.py       # Maps approved actions to AppiumActions
    └── targets.py        # Durable targets, ranked resolution, and locator traces

tests/autotests/ui/       # Contract checks, live scenario, and target catalogs
runs/                     # Ignored local execution evidence
```

Tests construct one `MobileDevice` from the active Appium session and the
appropriate target catalog. Application workflows call semantic operations
such as `device.ui.tap("settings.about_device")`; reviewed `AppiumActions`
still own the physical tap, swipe, wait, and evidence behavior. Platform-only
operations use the same facade, for example `device.settings.launch_root()`.

Read [architecture](docs/architecture.md), [MVP](docs/mvp.md), the
[Appium action contract](docs/appium-actions.md), and the
[model gateway guide](docs/model-gateway.md) before extending the system.
