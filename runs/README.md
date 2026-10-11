# Local agent run evidence

The agent loop writes one directory per attempt:

```text
<run-id>/
  scenario.json   # Goal, assertions, limits, and test-data reference names
  steps.jsonl     # Planned actions, observations, and normalized execution results
  result.json     # Pass, product failure, test failure, or blocked outcome
```

Screenshots and Appium UI-source files are referenced from the step records. Run
output is ignored by Git. Test-data values are never written to the scenario
artifact.
