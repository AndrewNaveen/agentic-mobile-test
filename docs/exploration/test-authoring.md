# Turning exploration evidence into pytest

[Workflow — author a test](../README.md#8-author-a-deterministic-test)

The next deliverable after exploration is a reviewable pytest candidate: one
explicit behavior, an observable assertion, prerequisites and cleanup. The coding
assistant reads the evidence and writes the candidate. The saved action trail
provides observations; it is not a script to replay verbatim.

## Review the evidence before choosing an assertion

- Verify screenshot and XML hashes against `exploration.json`.
- Compare the original objective, executed actions and before/after screens.
- Separate the control's label from the player's state. A Pause button offers a
  pause action; its label does not say the player is paused.
- Identify missing directions, uncertain effects and cleanup that was not observed.
- Obtain approval for the expected behavior before accepting the test as a product
  regression test. Observations can support a candidate; they do not define a requirement.

For the Home Assistant run `2026-10-21T205456.159567Z-100fa8db`, the six recorded
screenshot/XML hashes match. The recorded sequence is:

1. Overview shows `Living RoomPlaying`.
2. Opening the player shows a **Pause** button.
3. Tapping Pause changes the button to **Play**.

The model's review describes the reverse transition. Its finish message also
claims restoration, but the trace has no resume action or return to Overview.
Keep the original run unchanged and record these discrepancies in the candidate's
review. Resume, real audio playback and restoration remain unverified.

The narrow candidate assertion is: **given the isolated Living Room demo player
is playing, tapping Pause makes its playback control show Play.** This is a UI
assertion requiring approval, not proof that physical audio stopped. A future
backend-state assertion needs a separately reviewed state reader.

## Put each responsibility in the right place

| Responsibility | Location | Example |
| --- | --- | --- |
| Preconditions and restoration | App-local `conftest.py` | Verify the demo player starts playing; restore the original state after the test |
| The behavior and assertion | `test_playback.py` | Request Pause and require the Play control to appear |
| App selectors and navigation | Local functions in the test initially | Open Living Room and identify its playback control |
| Device operations and bounded waits | Existing `AppiumActions` | Tap a located element and wait for an explicit postcondition |

The first implemented candidate uses only:

```text
tests/autotests/ui/homeassistant/
  conftest.py
  test_playback.py
```

The [playback test](../../tests/autotests/ui/homeassistant/test_playback.py) and
[local fixtures](../../tests/autotests/ui/homeassistant/conftest.py) have passed
two consecutive real Appium sessions, with Gemini keys removed from the replay
environment. Both sessions restored Overview with Living Room playing. The second
session needed no manual preparation between runs. This validates the UI check
and its restoration on this demo; it does not establish physical audio behavior
or exhaustive playback coverage. Use [workflow step 9](../README.md#9-t1--replay-the-authored-test)
for the exact replay command.

Do not pause and resume through the UI in fixture setup to manufacture the
precondition for a pause test. Prepare the demo state separately and let setup
verify it. A missing precondition is not a product pass. Teardown restores state
with bounded operations and reports restoration failures without hiding the
original test failure.

## Grow reusable functions from working tests

Useful app-level operations might be `open_player(name)`, `pause_player()` and
`resume_player()`. Each needs explicit preconditions, an observable postcondition,
a fixed timeout and failure evidence. For example, `pause_player()` requires a
Pause control, invokes the existing tap operation and waits for Play to appear.

Start with local functions for the first candidate. When another test actually
needs the same behavior, extract the common functions and selectors into an
app-local module such as `media_player.py`. Playback semantics stay in that app
module; generic taps and waits stay in `AppiumActions`.

Review exploration locators before using them: screen-local `e009` references
expire, generated XPath may encode incidental hierarchy, and `Living RoomPlaying`
combines identity with a changing state. Prefer stable app identifiers and
player-scoped controls. Validate the selected locators in the real Appium replay.

## Use replay feedback to improve the candidate

Run the candidate on the isolated app with an approved expectation. Compare the
actual result with that expectation, inspect failure evidence, and fix selectors,
setup or code when the evidence supports the fix. Keep genuine product failures
visible; do not weaken the assertion to obtain a pass. Do not introduce hidden
model-driven recovery into the deterministic test.

A pause test does not establish resume coverage. Add a separate resume candidate
when its expectation and prerequisites are defined, then validate it through its
own real replay. Repeated runs from declared starting states can reveal state
leakage; they do not prove the test will never be flaky.

The author-run-inspect-fix loop follows the verification approach described by
[LangChain](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering).
Checking actual saved state rather than the agent's success claim follows the
outcome distinction in [Anthropic's evaluation guidance](https://www.anthropic.com/research/demystifying-evals-for-ai-agents).
Applying those ideas to this Appium workflow is our design proposal, not a mobile
testing result established by those articles.
