# Model Gateway Guide

This guide records how Gemini will connect to the agentic discovery loop and
what to do each time you work on the project. Deterministic regression tests do
not require Gemini.

## Current Status

- Google AI Studio project: `artemis-explore`
- Billing: Prepay with auto-reload disabled
- Intended model: `gemini-3.5-flash-lite`
- Existing local key: `.artemis/.env`
- Gemini gateway: implemented with offline contract tests

The Artemis runtime is reference material only. Do not launch it as part of
this framework: its configuration uses different models and permits unbounded
turns. We may reuse the API credential, but not its agent runtime.

## One-Time Google Setup

1. Create a Gemini API key in Google AI Studio.
2. Use Prepay billing and keep auto-reload off.
3. Optionally set a small project monthly spend cap on the AI Studio **Spend**
   page. Billing enforcement can lag, so this is not the only safeguard.
4. Never commit, print, paste, or log the API key.

The model is selected in each API request, not on the billing page. The billing
page's model selector only filters cost reporting.

## Start of Every Work Session

From the repository root:

```bash
cd /Users/andrewsekar/repos/agentic-mobile-test
source .venv/bin/activate

GEMINI_API_KEY="$(sed -n 's/^GEMINI_API_KEY=//p' .artemis/.env)"
export GEMINI_API_KEY
test -n "$GEMINI_API_KEY" && echo "Gemini key loaded"
```

Do not run `echo "$GEMINI_API_KEY"`. The export lasts only for the current
terminal. A new terminal requires repeating these steps.

Confirm the emulator before a live mobile run:

```bash
adb devices
```

Run normal offline checks with:

```bash
pytest
```

Install the optional Gemini SDK once in the project environment before the
first model-backed experiment:

```bash
python -m pip install -e '.[gemini]'
```

Normal pytest never calls Gemini. The connection experiment requires both its
marker and the explicit paid-request option:

```bash
pytest -m gemini --run-gemini
```

## Gateway Safety Contract

The `GeminiGateway` enforces:

- model fixed by default to `gemini-3.5-flash-lite`;
- at most 10 model calls per run;
- at most 200 output tokens per call;
- a small estimated per-run cost limit, initially `$0.02`;
- no automatic retries;
- immediate stop on authentication, quota, billing, or schema errors;
- redacted logs that never contain credentials or sensitive entered text;
- a strict structured response containing one proposed action.

These defaults are implemented in `GeminiBudget`. The dollar value is a local
estimate based on configured token prices, not a replacement for Google billing
controls. Update the prices when the selected model's published pricing changes.

The gateway only communicates with Gemini. It does not execute Appium actions,
change assertions, determine the verdict, or silently fall back to Artemis.

## Intended Runtime Flow

```text
Appium observation (screenshot + compact element list)
                         ↓
                 StructuredPlanner
                         ↓
                  GeminiGateway
                         ↓
             tap / scroll / finish proposal
                         ↓
                  ActionPolicy
                         ↓
           AppiumExecutor → AppiumActions
                         ↓
             deterministic verification
```

Send only the current screenshot, compact observed elements, a short recent
action summary, and the remaining step budget. Do not repeatedly send complete
UI XML, old screenshots, source code, or full logs.

## Billing and Error Expectations

- `429 RESOURCE_EXHAUSTED`: quota or rate limit reached. Stop the run; do not
  add an unbounded retry loop.
- `402 Payment Required`: prepaid credit is exhausted. Stop until credits are
  deliberately added.
- `$0` prepaid balance: Gemini API calls stop. They do not fall back to the free
  tier.
- Auto-reload off: Google should not automatically purchase more credits.
- Billing and spend-cap enforcement can lag by roughly ten minutes, so local
  call and cost limits remain mandatory.

## End of a Session

Review AI Studio usage when a live experiment was run. Close the terminal or
remove the key from the current shell:

```bash
unset GEMINI_API_KEY
```

Keep generated evidence under `runs/`; do not commit it. Record the selected
model, model-call count, token usage, estimated cost, scenario version, and
final outcome for every model-backed run.
