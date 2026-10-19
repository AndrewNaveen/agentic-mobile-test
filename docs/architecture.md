# Architecture

The active authoring path is exploration, evidence review, and coding-assisted
pytest authoring. No prebuilt replay tests remain; future deterministic tests must not call the model.

## Runtime responsibilities

- `ExplorationLoop`: bounded decisions, observations, attempts and report persistence.
- `ExplorationPlanner`: supplies objective, current screenshot, compact XML and
  history to the gateway.
- `prompts/exploration.md`: single packaged investigation instruction, loaded
  once per planner and copied/hash-recorded with each run. User briefs stay separate.
- `investigation.py`: records a candidate and evidence-linked reviews. These
  are hypotheses/assessments, not product verdicts.
- `ActionPolicy`: checks permitted actions, targets and repetition.
- `AppiumObserver`: captures settled screenshots/XML and resolves executable refs.
- `AppiumExecutor`: maps permitted actions to existing `AppiumActions`.
- `GeminiGateway`: structured model responses and local call/cost limits.
- `completion.py` and `prompts/completion.md`: separate completion-review request
  with original brief, action trail, XML and all recorded screenshots. The loop
  accepts completion only after review and reports gaps for a human decision.
  Review has a separate reserved one-call budget, runs after handled stops, and
  never restarts exploration. Original exploration stops are preserved. This is not a
  deterministic product oracle or a second device-controlling agent.
- Device facade and target catalogs: optional conveniences for deterministic tests.

## Authoring responsibilities

The coding assistant reviews saved actions and evidence, identifies repeatable
setup and cleanup, and writes a pytest candidate. Engineers review product
expectations and approve live execution. Fixtures own setup/cleanup; tests show
actions and assertions. Reusable device operations remain in src.

## Boundaries

No scenario-driven AgentLoop or automatic template generator remains active.
A report's completed status is not correctness, coverage or human approval.
The current explorer still has a one-candidate restriction; removing that and
adding richer experiment planning are separate behavioral changes.
Protected Appium action contracts were not changed during cleanup.
