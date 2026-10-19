# Agentic Mobile Test

**LLM-guided mobile UI exploration, grounded in Appium evidence.**

> Work in progress. An experimental Android testing project, not a production-ready autonomous QA system. Interfaces and workflows are evolving.

## What I'm building

A faster path from an unfamiliar mobile workflow to a reviewed, repeatable test.
An engineer describes what to investigate and sets boundaries. Gemini observes
the app, chooses actions, and investigates through Appium. The framework records
what happened and asks a separate model request to review the evidence against
the original objective.

The direction is **agentic discovery followed by deterministic regression**:
a coding assistant turns reviewed evidence into pytest tests that run without
an LLM. That handoff is currently manual and coding-assisted—not an automatic
test generator.

## Why use an LLM here?

Test authoring starts before assertions: learning the app, finding controls,
understanding transitions, identifying prerequisites and reproducing a journey.
A changed workflow can require repeating much of that investigation.

An LLM can choose its next step from the current screenshot and UI hierarchy
instead of requiring an engineer to prewrite every navigation step. The intended
benefits are:

- **Faster workflow investigation:** discover routes and controls from a brief.
- **Less preparation for test authoring:** hand an engineer or coding assistant
  recorded actions, resolved locators and before/after evidence.
- **Clearer failure triage:** retain rejected actions, partial progress and
  uncertainty instead of reporting unsupported success.

These are engineering goals, not measured productivity claims. The model does
not replace product requirements, environment setup or reliable assertions.

## How it works

1. **Describe:** supply an objective, app package, boundaries and limits.
2. **Observe:** Appium captures a settled screenshot and Android UI hierarchy.
3. **Decide:** Gemini selects a structured action using observed element references.
4. **Validate and act:** code checks permissions and targets; Appium executes.
5. **Repeat:** capture the resulting screen and continue within bounded limits.
6. **Review:** a separately budgeted model request examines the original brief,
   actions and evidence—even when exploration exhausts its budget.
7. **Hand off:** a human decides whether to investigate further or author a
   deterministic pytest candidate from the evidence.

The reviewer cannot restart exploration. Its assessment is not a product verdict.
Natural-language boundaries do not replace an isolated test environment.

## What works today

- Android exploration through Appium with Gemini structured responses.
- Screenshot/XML evidence, action records, prompt snapshots and evidence hashes.
- Guarded target resolution and bounded correction feedback.
- Separate exploration/review budgets and explicit paid-run opt-in.
- A Home Assistant demo investigation that exercised a player's Pause/Play UI.

During recent validation, automatic review encountered an upload timeout; a
separately authorized review-only request subsequently completed. This is a
working prototype with visible failure modes, not a reliability benchmark.

## Try it

Follow [installation](docs/prerequisites.md), then the
[Home Assistant demo](docs/examples/home-assistant/README.md).
The [general workflow](docs/workflow/README.md) explains briefs, outputs and handoff.

The example allows 15 exploration decisions with an estimated $0.02 budget,
plus one final review with a separate $0.02 allowance: **$0.04 combined per run**.
These are local estimates, not provider-enforced billing caps. Failed requests
may have unknown charges. Screenshots and UI text are sent to the configured
provider: use demo accounts and non-sensitive data.

## Limitations and next steps

- Android is the exercised platform; other platform helpers are not a validated promise.
- Exploration supports tap, scroll and back, with one candidate hypothesis per run.
- Cleanup is caller-owned. Backend state and physical behavior are not verified.
- Explorer and reviewer both use Gemini; separate context does not eliminate model error.
- No maintained unit-test suite, CI quality gate or prebuilt replay suite currently ships.
- Next: reduce repeated context, evaluate review accuracy, restore regression
  coverage, and validate evidence-to-pytest handoff across more workflows.

## Explore the code

| Area | Responsibility |
| --- | --- |
| `src/agentic_mobile_test/agent/` | Orchestration, action policy and review contracts |
| `src/agentic_mobile_test/appium/` | Observation, target resolution and UI execution |
| `src/agentic_mobile_test/gateways/` | Gemini requests, usage accounting and budgets |
| `src/agentic_mobile_test/prompts/` | Versioned explorer and reviewer instructions |
| `tests/conftest.py` | Appium sessions and explicit execution options |
| `tests/autotests/ui/exploration/` | Generic pytest exploration entry point |
| `runs/` | Ignored local evidence, not public sample data |

Read the [architecture](docs/architecture.md), [Appium contracts](docs/appium-actions.md)
and [gateway notes](docs/model-gateway.md). Feedback on evidence quality, failure
handling and reproducibility is welcome. Not affiliated with Google, Appium or
Home Assistant.
