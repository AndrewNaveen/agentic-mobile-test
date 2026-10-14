# Local agent run evidence

The agent loop writes one directory per attempt:

```text
<run-id>/
  scenario.json   # Goal, assertions, limits, and test-data reference names
  steps.jsonl     # Planned actions, observations, and normalized execution results
  result.json     # Pass, product failure, test failure, or blocked outcome
  discovered-path.json # Passed path candidate for human-reviewed regression generation
  lifecycle.json  # Settings fixture setup and cleanup checkpoints
```

Screenshots and Appium UI-source files are referenced from the step records. Run
output is ignored by Git. Test-data values are never written to the scenario
or discovery artifacts. `discovered-path.json` is written only after every
declared assertion passes; it contains observed targets, candidate locators,
before/after evidence paths and hashes, and verifier results. It requires human
review and is not generated pytest code.
