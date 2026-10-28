# Appium action layer

[Workflow](../README.md)

`AppiumActions` provides deterministic touchscreen operations for pytest tests.

Current operations:

- wait for an element and tap it
- tap a percentage position inside an element
- tap screen coordinates
- clear and type text
- long press
- swipe with absolute points or screen fractions
- scroll a bounded number of times until an element is visible
- dismiss known overlays
- press Back
- set a slider to an absolute percentage with bounded correction
- experiment with one short slider drag, retaining before/after evidence
- capture a screenshot and Appium UI source

Action execution failures raise `AppiumActionError` with failure evidence when
capture succeeds. Successful actions can also capture before/after evidence.

The example assumes a pytest `driver` fixture and a product-specific
`read_volume_from_product_test_interface` function.

```python
from pathlib import Path

from appium.webdriver.common.appiumby import AppiumBy

from agentic_mobile_test.appium import AppiumActions, OverlayRule


actions = AppiumActions(
    driver,
    evidence_dir=Path("runs/current-test/actions"),
    record_successful_actions=True,
)

banner = OverlayRule(
    container=(AppiumBy.ID, "com.example:id/banner"),
    dismiss=(AppiumBy.ID, "com.example:id/banner_close"),
)

actions.tap(
    (AppiumBy.ACCESSIBILITY_ID, "Audio settings"),
    overlays=(banner,),
)

result = actions.set_slider_value(
    (AppiumBy.ID, "com.example:id/volume"),
    60,
    overlays=(banner,),
    independent_reader=read_volume_from_product_test_interface,
)

assert result.independent_percent is not None
```

The slider method calculates absolute screen coordinates from the slider's
actual bounds. It reads the value after each movement and stops after the
configured attempt limit. A product-specific reader can independently verify
that the underlying value changed.

Exploration uses this same method through `set_slider_value`, with a current
slider reference and `target_percent` from 0 to 100. Its policy requires explicit
permission in the brief's `allowed_actions`; direct taps on recognized sliders
are rejected. Duplicate slider IDs are resolved through unique container anchors,
and ambiguous sliders remain non-executable. The model never supplies coordinates
or raw locators. Reports retain the target, observed values, correction count and
failure evidence. An unreadable value stops for guidance.

## Experimental slider drag

The Home Assistant demo exposes slider bounds and screenshots but no numeric
values through native Appium. `set_slider_value()` correctly refuses an exact
value claim in that situation. A raw screen swipe has no slider identity or
element-relative limits. Exploration needs a common operation for a bounded
gesture whose product effect remains unverified.

Method on `AppiumActions`, reusable by exploration and pytest:

```python
def drag_slider(
    self,
    locator: Locator,
    start_percent: float,
    end_percent: float,
    *,
    duration_seconds: float = 0.5,
    timeout_seconds: float = 10.0,
) -> ActionResult:
    ...
```

`start_percent` and `end_percent` are horizontal positions within the slider's
current bounds, from 0 to 100. They are not volume or playback values. For example,
80 → 60 requests a short leftward drag; it does not claim volume changed from
80% to 60%. Gemini may estimate the starting thumb position from the screenshot;
that estimate remains recorded as a gesture input, never an observed product value.

### One call, one bounded experiment

1. Validate finite numeric inputs, with positions in 0–100, movement between 1
   and 30 percentage points, duration in 0.1–1.0 seconds and timeout in (0, 10].
2. Wait up to the timeout for exactly one visible, enabled, recognized horizontal
   slider. Multiple matches fail immediately. Use its current bounds; reject
   invalid bounds, off-screen points or endpoints that round to the same pixel.
3. Capture the screenshot and XML before the action. Read a numeric value if the
   existing reader can expose one; a missing value is recorded as unavailable.
   Other reading errors remain errors.
4. Calculate X coordinates as fractions of the current element width and use
   element-center Y. Perform one W3C touch drag using the existing gesture
   implementation. There are no automatic retries or correction movements.
5. Capture after-action screenshot/XML and any available value. Return
   `ActionResult` with the bounds, requested positions, actual points, available
   values and evidence. Mark the command outcome `gesture_returned` and product
   value verification `unverified`; returning from Appium is not a product pass.
6. Exploration takes its existing settled observation before Gemini chooses
   another action, with the existing 10-second settling limit. A timeout or an
   unexpected app change stops the run with the attempted action preserved.

Invalid inputs fail before movement. Interaction or evidence-capture failures
raise `AppiumActionError` and retain failure evidence when capture succeeds.
An unchanged screen is valid experimental evidence of no demonstrated effect,
not a reason to retry automatically. Unknown dialogs are not dismissed as recovery.

### Permissions, interpretation and restoration

- Expose `drag_slider` with a current slider ref plus `start_percent` and
  `end_percent`. Gemini supplies neither raw screen coordinates nor locators.
- Require explicit `drag_slider` permission in `allowed_actions`; retain the
  existing step, cost and repeated-ineffective-action limits.
- Include the start/end positions in action signatures. Permit at most two
  consecutive identical probes even when image pixels change: native XML can
  remain unchanged while a thumb moves, and unrelated animations are not proof
  that the slider responded.
- Gemini compares the observations and records the visible effect, uncertainty
  and next experiment. It cannot convert estimated track positions into verified
  product values or certify real audio effects from thumb movement.
- Capture the initial state for cleanup. Returning to an estimated thumb position
  does not establish exact restoration; keep restoration unverified until an
  observable value or approved independent check confirms it.
- Preserve the exact-value `set_slider_value()` contract. The approved
  experimental exception in AGENTS.md permits this operation:
  an evidence-producing drag may return with product value verification unknown.
  Deterministic value-setting tests still require verified values.

### Platform scope

The first implementation supports horizontal Android `SeekBar` and iOS
`XCUIElementTypeSlider` controls through the same W3C gesture. Recognition and value
attributes differ by platform. Do not use Android-only attributes on iOS. Vertical,
rotated and right-to-left semantic mappings remain unsupported unless reviewed;
the gesture inputs always describe physical left-to-right bounds.

Live Android validation on the Home Assistant demo observed the lower slider's
thumb move left and return to its visible starting position. Numeric values and
exact restoration remained unverified. iOS has not been validated on a device.
