# First vertical slice

The MVP should prove one claim:

> A model can navigate one Android journey from live observations through a
> constrained Appium tool layer, while deterministic code controls actions,
> evidence, and the final verdict.

## Included

- Android Settings and the journey from its root screen to About phone.
- One model provider behind `ModelGateway`.
- Screenshot plus UI-hierarchy observation.
- Semantic element references with accessibility-first grounding.
- Four possible actions: tap, type approved test data, bounded scroll, and Back.
- A fixed step budget and ineffective-action limit.
- At least one deterministic success assertion.
- Screenshots, UI source, step trace, and a classified result.
- Repeated clean-state runs and one intentionally seeded product failure.

## Excluded

- Multiple applications, iOS, cross-app workflows, or device farms.
- Page-object generation, dashboards, databases, MCP, and multi-agent graphs.
- LLM-authored assertions during execution.
- Unreviewed coordinate tapping or silent self-healing.

## Acceptance checks

1. A high-level goal reaches the expected screen without a prewritten workflow.
2. Every executed interaction maps to a reviewed `AppiumActions` method.
3. Unknown targets, invented fields, disallowed actions, and repeated ineffective actions fail visibly.
4. The independent assertion—not the planner—decides whether the run passes.
5. Evidence explains each action and the observed result.
6. Ten clean-state runs report pass rate, false failures, average steps, and duration.
7. A seeded application defect is detected rather than navigated around or silently healed.

## Current baseline

`tests/autotests/ui/android_settings/test_android_settings.py` implements the
same journey deterministically. It uses a reviewed semantic target to establish
that Appium, pytest, evidence capture, and the destination assertion work
without model uncertainty.

## Test layout

- `tests/conftest.py` configures Appium once per pytest run and creates a fresh
  WebDriver session for each test.
- `tests/autotests/ui/conftest.py` establishes Android Settings state and
  captures setup/cleanup evidence for UI journeys.
- `tests/unit/` covers contracts and orchestration offline; `tests/integration/`
  contains explicitly enabled live provider checks; device journeys live under
  `tests/autotests/ui/`.

Use behavior-specific test names such as
`test_add_device_shows_connection_error`. Express visible/absent text as
assertion expectations in a fixed scenario contract, not generic test functions
like `test_something_exists`. An absence assertion must follow the action under
test; an initially absent message alone is not evidence of a negative result.
