# Model gateway reference

Start with the [workflow](workflow/README.md); installation and key setup are
in [prerequisites](prerequisites.md).

`GeminiGateway.choose_exploration` is the active model entry point. It returns
structured actions or investigation notes; it cannot execute Appium itself.
The only retained runner is exploration; no provider smoke test remains.

## Implemented limits

`GeminiBudget` currently defaults to model `gemini-3.5-flash-lite`, 10 calls,
200 output tokens per response and an estimated $0.02 ceiling.
The exploration pytest entry point overrides calls with the brief's
`max_steps` and output tokens with 600. The example has 15 decisions.
Exploration has its own $0.02 estimate. Final review has a separate one-call,
1000-output-token, $0.02 allowance: $0.04 combined estimated ceiling per run.
Review is attempted once after any handled stop when screen evidence exists,
including exploration budget exhaustion. Its token preflight includes all saved
screenshots/XML. Review cannot restart exploration or override an error/budget stop.
Oversized input, malformed output or provider failure records review_unavailable;
there are no automatic retries. HTTP timeout is 30 seconds for exploration and
60 seconds for the larger multi-screenshot review request, not a whole-run deadline.
Failed requests with unknown usage are counted under unaccounted_calls; their
possible charges are excluded from the recorded estimate, not assumed to be zero.
That gateway refuses further requests when usage is unknown.

Token preflight and configured price estimates bound requests. SDK automatic
retries are disabled. Provider errors stop the run; do not add billing workarounds.
These controls are not a provider-enforced dollar cap. Verify configured prices
when changing models. Do not infer account billing status from this repository.

Keys belong only in the ignored .env/environment. Never print them. Evidence may
contain sensitive UI content and is not automatically redacted.
