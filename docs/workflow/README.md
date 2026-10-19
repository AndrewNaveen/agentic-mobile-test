# Exploration workflow

This is an experimental workflow, not an unattended product-test gate.
For a complete worked setup, use the [Home Assistant demo](../examples/home-assistant/README.md).
Install the shared prerequisites using [installation](../prerequisites.md).

## 1. Prepare an isolated app

Use a demo account, app build and device that are safe to change. Log in manually
and record the initial state and how to restore it. Do not let exploration touch
production accounts or real devices. Setup and cleanup are not discovered reliably
or performed automatically.

## 2. Write an exploration brief

Copy [the example brief](examples/home-assistant-media-player.json) for your app.
Describe the investigation, not every tap or locator:

```json
{
  "objective": "Find a demo media player, investigate playback controls, exercise one behavior and report the evidence and uncertainties.",
  "app_package": "io.homeassistant.companion.android",
  "boundaries": ["Demo players only; do not change account or server settings"],
  "cleanup": "Restore the original playback state and return to Overview",
  "sandbox_confirmed": true,
  "max_steps": 15,
  "allow_toggle_changes": true
}
```

Set sandbox_confirmed only after checking isolation. A brief cannot add missing
tools: exploration currently supports tap, scroll and back. A candidate criterion
is a hypothesis unless supported by supplied requirements.

## 3. Run explicitly

Activate the virtual environment, load your ignored .env, start the emulator and
Appium, then run the exploration pytest entry point. Use the
[demo's full command](../examples/home-assistant/README.md#6-review-the-brief-and-run-exploration)
as a starting point; change the brief, device, package and resolved launch activity.

Paid execution requires `--run-gemini`. Exploration has a $0.02 estimated budget;
one final review has a separate $0.02 allowance. These are local estimates, not
provider billing caps. No automatic retries or post-review restarts occur.

## 4. Review evidence, not the pytest badge

The terminal prints the absolute exploration.json path. In that directory inspect:

- `report.md`: investigation, final review and unresolved gaps.
- `exploration.json`: original brief, attempts, stop reasons, budgets and usage.
- `actions.jsonl`: proposed, rejected and executed actions.
- `screens/`: screenshot/XML evidence and hashes referenced by the report.
- `system-prompt.md` and `completion-prompt.md`: exact instructions used.

A completion review is attempted after handled stops when evidence exists, including
budget exhaustion. Review failure preserves evidence as review_unavailable.
An exploration stop is not erased because a reviewer considers the work sufficient.
A completed result is not proof of product correctness.

## 5. Decide what happens next

Restore changed state manually. Review the missing evidence and decide whether to
authorize another experiment, clarify expectations or author a deterministic test.
The reviewer never grants itself a new execution budget.

For test authoring, give a coding assistant the report and this request:

```text
Read AGENTS.md and the exploration report at <absolute path>.
Verify evidence hashes and inspect the recorded actions and screenshots/XML.
Separate observed behavior from assumptions.
Propose the prerequisites, local setup/cleanup fixture and deterministic assertions.
After review, write a pytest candidate using the existing Appium helpers.
Do not depend on Gemini or the original report at replay time.
Do not run paid requests or live device tests without approval.
```

There is no generator CLI or maintained replay suite yet. Repeatability and
CI suitability must be established by running and reviewing the resulting test.
