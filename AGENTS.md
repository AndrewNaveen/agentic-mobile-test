# Project purpose

Build a small, inspectable agentic mobile-testing system that demonstrates how
an LLM can navigate from a high-level QA goal while deterministic code controls
actions, evidence, and the final verdict.

The first objective is understanding and proving the agent loop, not building a
complete enterprise platform. Approved scenarios run through pytest. A runtime
planner may choose among bounded semantic actions, but it may not rewrite the
scenario, assertions, permissions, or expected result.

# Terms

Use these names precisely:

- **pytest** is the test runner and owns fixtures, test lifecycle, and assertions.
- **Appium** is the low-level mobile driver.
- **AppiumActions** is our deterministic helper class on top of Appium. Do not
  call this class a driver.
- **AgentLoop** owns the bounded observe-plan-policy-act-verify cycle.
- **StructuredPlanner** is the strict boundary to a future model provider.
- **Artemis** is reference material only, not a project dependency or runtime.
- Avoid the generic word **backend** when the specific component name is clearer.

# Current scope

- Use Python and pytest. Do not add a custom project CLI unless the user agrees
  that pytest cannot handle the requirement.
- Keep tests under `tests/autotests/ui/`.
- Keep deterministic contract checks and the future live scenario in the
  current test tree. Do not create `unit`, `smoke`, or `regression` trees yet.
- Start with one Android application and one meaningful journey.
- Do not add a database, RAG, MCP, web dashboard, registry service, review UI,
  or multi-agent framework without a demonstrated need and user agreement.
- Keep the model boundary provider-neutral until the user selects a provider.
- Normal pytest checks must run without network access or paid model calls.

# Architecture boundaries

- A runtime LLM may select one action at a time from the current observation.
- Executable steps must map to reviewed functions exposed by the deterministic
  action layer.
- Do not put LLM calls or visual grounding inside `AppiumActions`. A future
  locator-free grounding component must produce a bounded, reviewable target
  that the action layer can execute and record.
- An LLM must not guess screen coordinates, emit Appium selectors, invent
  gestures, add retries, skip assertions, or change expected results.
- The planner targets opaque references from the current observation. The
  observer and policy decide whether a reference has a safe executable locator.
- If an existing action cannot perform a requested interaction, expose that gap
  for review. Do not generate an improvised raw device command to get past it.
- App-specific locators, workflows, and business assertions do not belong in
  `AppiumActions`.
- Product state verification should use deterministic UI assertions or an
  independent product test interface when one is available.
- A tool reporting `succeeded` is an execution signal, not proof that the
  product met the expected result.

# Protected low-level action workflow

`src/agentic_mobile_test/appium/actions.py` and the public types in
`src/agentic_mobile_test/appium/models.py` define the low-level interaction
contract. Do not add or change a low-level operation merely to make one scenario
pass.

Before adding an operation or changing its behavior:

1. Inspect the existing implementation and the real UI problem.
2. Present the problem to the user before editing these files.
3. Describe one concrete example and why the existing operations are
   insufficient.
4. Propose the public method signature and arguments.
5. Explain the deterministic algorithm, bounds, timeout, retry limit,
   postcondition, evidence, and failure behavior.
6. Identify Android and iOS differences when they affect the contract.
7. Iterate on that design with the user and wait for agreement.
8. Implement the smallest reusable change after agreement.

A narrow refactor or defect fix that preserves an already approved contract
still requires stating the defect and expected behavior before editing. Do not
silently change coordinates, timing, retry behavior, or verification rules.

# Rules for deterministic UI operations

- Use explicit state waits. Do not use arbitrary sleeps as synchronization.
- Every loop, wait, scroll, retry, and recovery path must have a fixed limit.
- Use current W3C actions or supported Appium mobile commands. Do not introduce
  deprecated `TouchAction` or `MultiAction` APIs.
- Validate coordinates and percentages before sending an action to Appium.
- Calculate coordinates from current element or screen bounds. Do not mix
  percentages, offsets, and absolute pixels.
- Use element-center Y coordinates for horizontal controls unless the reviewed
  control contract says otherwise.
- Handle known overlays through explicit rules. Do not silently tap through an
  unknown obstruction or dismiss an unexpected dialog without an allowed rule.
- Never swallow an interaction exception. Raise a useful error so pytest cannot
  record a false pass.
- Do not use `assert False` inside the action library. Return a structured result
  on success and raise a typed exception on failure.
- A successful Appium command does not prove a successful product action. Use a
  deterministic postcondition when the action changes meaningful state.
- Capture a screenshot and UI source on interaction failure. Capture checkpoint
  evidence on success when the test requires it.
- Do not place credentials, entered secret text, or tokens in logs or action
  result details.

For sliders and other precise controls:

- Express the requested value as an absolute target.
- Read the current value when the UI exposes one.
- Calculate start and end points from the control's current bounds.
- Read the resulting value after movement.
- Permit only a small, fixed number of correction attempts.
- Support an independent value reader when UI appearance is not sufficient.
- Fail when the value cannot be observed or verified. Do not assume movement
  succeeded because Appium accepted the gesture.

# Test creation and regression

Creation is an authoring workflow:

1. Start from a high-level QA scenario.
2. Identify preconditions, business intent, checkpoints, assertions, allowed
   recovery, and evidence.
3. Define allowed semantic actions and map them to deterministic operations.
4. Expose any missing operation using the protected workflow above.
5. Produce a candidate pytest test or test contract for human review.
6. Approve a specific version.

Regression is an execution workflow:

- Run the exact approved version.
- Do not rewrite the test or expected result while it is running.
- Treat a requested behavior change as a new version requiring review.
- Freeze preconditions, business intent, critical checkpoints, assertions,
  boundaries, and recovery policy.
- The runtime planner may adapt low-level targeting and noncritical navigation
  within the frozen budget and action allowlist. Expected outcomes may never
  adapt.

Keep these four outcomes distinct:

- **Pass:** execution completed and every required assertion passed.
- **Product failure:** the product was reached and a required behavior or value
  was wrong.
- **Test failure:** the test contract, locator, action, or verification code
  could not produce a trustworthy result.
- **Blocked:** a required device, application build, fixture, account, service,
  or precondition was unavailable.

# Evidence

- Save run artifacts under `runs/`.
- Evidence must be associated with the test version and execution attempt.
- Preserve the requested scenario, normalized action results, explicit
  assertions, screenshots, UI state, and relevant errors.
- Do not accept an LLM explanation as evidence by itself.
- Never report omitted, interrupted, or quota-exhausted attempts as passes.

# Dependencies and local tools

- Use the repository `.venv` for pytest and Appium Python dependencies.
- Declare project packages in `pyproject.toml`; use compatible pinned versions
  for interaction-critical packages.
- Update setup documentation when dependency or startup steps change.
- Do not install or change global tools, shell configuration, Homebrew packages,
  Android SDK components, or system services without explicit user permission.
- Never commit API keys, credentials, local research-tool data, emulator data,
  or generated run evidence unless the user explicitly requests a fixture.

# Validation

- Keep changes small enough to review.
- Run compilation, focused linting, dependency checks, and the configured pytest
  suite after code changes.
- Use deterministic fakes to check planning contracts, policy, orchestration,
  evidence, calculations, and failure handling. Do not claim a gesture or
  scenario works until it has run through a real Appium session.
- Report what was actually exercised, including skipped tests and missing live
  validation.
- Do not add test files outside `tests/autotests/ui/` under the current scope.

# Communication

- Use plain language and concrete examples.
- State the problem before proposing a new abstraction.
- Keep explanations focused; do not bury the decision in architecture jargon.
- When discussing a low-level action, show what pytest requests, what Appium
  performs, what is observed afterward, and how failure is classified.
