# Local evidence

Exploration writes `exploration/<run-id>/` containing brief.json, exploration.json,
report.md, actions.jsonl, system-prompt.md, completion-prompt.md and numbered
screens with PNG/XML evidence. exploration.json includes completion reviews,
their gaps, the original exploration stop, separate exploration/review usage,
and the combined estimated cost. A terminal review never restarts exploration.
The terminal prints the report path. Partial and rejected attempts are retained.
Completion is not a product verdict. Cleanup is currently manual.

All run output except this README is ignored by Git and may contain private data.
