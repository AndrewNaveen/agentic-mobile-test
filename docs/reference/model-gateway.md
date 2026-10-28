# Model gateway

[Workflow](../README.md)

`GeminiGateway` sends structured requests to Gemini and accounts for calls,
tokens and estimated cost. It authenticates with `GEMINI_API_KEY` from the environment.

## Request limits

The configured model is `gemini-3.5-flash-lite`.

| Configuration | Call limit | Maximum output tokens per response | Estimated cost limit | Request timeout |
| --- | --- | --- | --- | --- |
| Gateway defaults | 10 | 200 | $0.02 | 30 seconds |
| Exploration runner | Brief's `max_steps` | 600 | $0.02 | 30 seconds |
| Final review | 1 | 1000 | $0.02 | 60 seconds |

The timeouts apply to individual HTTP requests, not the whole run.
Final review has its own gateway and budget; it can run after exploration stops
or exhausts its budget.

## Cost accounting

- Token preflight checks projected input and maximum output against the local cost limit.
- SDK automatic retries are disabled.
- Cost limits use configured price estimates; they are not provider-enforced billing caps.
- Failed requests with unknown usage increment `unaccounted_calls`. Their possible charges are excluded from the estimate.
- A gateway with unknown usage refuses further requests.

Reports save exploration usage under `model_usage`, final review usage under
`review_usage`, and the combined estimate under `total_estimated_cost_usd`.

## Review failures

Final review includes saved screenshots, compact UI source and the action trail.
Missing evidence, oversized input, malformed responses or provider errors can
leave the review unavailable. The runtime preserves the evidence and recorded error.
