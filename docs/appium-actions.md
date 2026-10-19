# Appium action layer

`AppiumActions` contains deterministic touchscreen operations for pytest tests.
It does not decide what a test should do. `ExplorationPlanner` proposes one
semantic action, `ActionPolicy` validates it, and `AppiumExecutor` maps it to an
existing method here. The planner never receives or supplies the Appium
locator.

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
- capture a screenshot and Appium UI source

Every failed operation raises `AppiumActionError`, so pytest fails instead of
continuing after a broken interaction. Failure evidence is written immediately.
Successful actions can also capture before/after evidence.

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
