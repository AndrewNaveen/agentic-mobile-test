# Agentic Mobile Test

A Python/pytest proof of concept for automating a clear mobile UI task:

1. Describe one UI task, its expected result and the starting state you know.
2. Gemini observes the screen and discovers actions through Appium.
3. Deterministic assertions check the result; the framework saves the path and evidence.
4. The generator converts a successful path into a pytest candidate.
5. An engineer adds repeatable setup/cleanup, reviews it and runs replay without Gemini.

Start with one task and an expected result you understand. No scenario-authoring
skill or positive/negative/edge brainstorming is required.
You do not need to design reusable fixtures upfront. Use discovery evidence to
decide what state preparation the repeatable test needs.

## Setup

Complete [first-time prerequisites](docs/prerequisites.md) once: Python
dependencies, Android emulator, project-local Appium and its driver, and a
Gemini API key. Create the ignored key file if needed:

```sh
cd /Users/andrewsekar/repos/agentic-mobile-test
test -f .env || cp .env.example .env
```

Edit `.env` to set your key before loading it.

At each session, start the emulator and run:

```sh
cd /Users/andrewsekar/repos/agentic-mobile-test
source .venv/bin/activate
adb devices
set -a
source .env
set +a
test -n "$GEMINI_API_KEY" && echo "Gemini key loaded"
```

Pytest starts Appium on port **4725** when needed. To run it manually for logs,
use `npm run appium:start` from the repository root in another terminal.
Reuse an existing server instead of starting another on the same port.

## Discover a task and validate its generated replay

Follow the [task-to-replay guide](docs/workflow/README.md). It covers defining
the initial task brief, saving the task contract, running one discovery,
reviewing evidence, generating Python, and validating replay.

The current runnable examples start in Android Settings. The existing YouTube
replay was written manually from the explored journey; it is not proof of a
completed generator-to-live-replay workflow. Validate a generated candidate
through the guide before claiming that end-to-end result.

## Offline checks

```sh
pytest tests/unit -q
```

No device or Gemini key is needed for these tests.

## Project map

- `src/agentic_mobile_test/` — agent loop, Appium/device operations, Gemini,
  assertions, evidence and generator.
- `tests/autotests/ui/` — live tasks, replay tests and UI fixtures.
- `tests/unit/` — offline checks; `tests/integration/` — opt-in provider checks.
- `runs/` — local discovery records, screenshots and UI snapshots.
