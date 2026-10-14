# Model Gateway Reference

For the complete start-to-finish project workflow, including scenario authoring,
emulator/Appium setup, Gemini discovery, and candidate generation, see the
[working guide](workflow/README.md). This page is the deeper reference for
Gemini configuration, cost controls, and gateway behavior.

This guide records Gemini's safety limits and gateway behavior. For the
repeat-every-session commands, use the [working guide](workflow/README.md);
first-time key and billing setup is in [prerequisites](prerequisites.md).
Deterministic regression tests do not require Gemini.

## Current Status

- Google AI Studio project: the project selected for this API key
- Billing: Prepay with auto-reload disabled
- Intended model: `gemini-3.5-flash-lite`
- Local key file: `.env` (ignored by Git)
- Gemini gateway: implemented with offline contract tests

## One-Time Google Setup

1. Create a Gemini API key in Google AI Studio.
2. Use Prepay billing and keep auto-reload off.
3. Optionally set a small project monthly spend cap on the AI Studio **Spend**
   page. Billing enforcement can lag, so this is not the only safeguard.
4. Never commit, print, paste, or log the API key.

The model is selected in each API request, not on the billing page. The billing
page's model selector only filters cost reporting.

## Load the Key in a New Pytest Terminal

From the repository root:

```bash
cd /Users/andrewsekar/repos/agentic-mobile-test
source .venv/bin/activate

set -a
source .env
set +a
test -n "$GEMINI_API_KEY" && echo "Gemini key loaded"
```

Do not run `echo "$GEMINI_API_KEY"`. The export lasts only for the current
terminal. A new terminal requires repeating these steps.

This export lasts only for the current terminal. Do not run
`echo "$GEMINI_API_KEY"`. Confirm the emulator before a live mobile run:

```bash
adb devices
```

Run normal offline checks with:

```bash
pytest
```

The SDK is installed during the one-time setup in [prerequisites](prerequisites.md).
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
controls. The Android Settings live test overrides these defaults with its
scenario step limit, 100 output tokens per call, and a `$0.005` estimated run
limit. Update the prices when the selected model's published pricing changes.

The gateway only communicates with Gemini. It does not execute Appium actions,
change assertions, or determine the verdict.

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
