# Working briefs and results

This folder holds **the briefs you give the explorer** and **the results it saves**.
A brief is a JSON file describing what to investigate and what changes are allowed.

## Working briefs

Create and edit briefs under the app's folder, for example:

```text
runs/app/home-assistant/brief.json
```

Pass that file to pytest using `--exploration-brief`. For another investigation,
create another brief in the same app folder.

Use the [brief template](../docs/exploration/brief-template.json) and
[workflow](../docs/README.md#5-t1--create-and-edit-your-brief) to prepare it.

## Generated results

The explorer creates a fresh folder for each execution:

```text
runs/apps/<app_slug>/<investigation_slug>/<run-id>/
```

The names come from your brief. Inside:

- **`report.md`** — findings and unresolved questions. Read this first.
- **`brief.json`** — the instructions used for that run.
- **`exploration.json` and `actions.jsonl`** — attempts, outcomes, evidence references and usage.
- **`screens/`** — screenshots and UI XML from the run.

`app/` holds briefs you edit; `apps/` holds generated results.
Reruns create new folders. Keep evidence from failed and partial runs too.
