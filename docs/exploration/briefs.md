# Exploration briefs

[Workflow — create your brief](../README.md#5-t1--create-and-edit-your-brief)

A brief is the JSON file you edit to tell the explorer what to investigate.
Use [brief-template.json](brief-template.json) for any app. Copy it to
`runs/app/<app-name>/` using workflow step 5, then edit the copy.

## Brief fields

Edit these fields, then save:

- **`app_slug`**: a short name for your app, such as `demo-app`.
- **`investigation_slug`**: a name for this objective, such as `playback-controls`. Use lowercase letters/numbers separated by single hyphens for both names, at most 80 characters.
- **`app_package`**: the installed Android package, replacing `com.example.demo`.
- **`objective`**: the behavior or question you want investigated. Describe the goal; the model chooses the navigation.
- **`boundaries`**: a non-empty list of allowed resources/actions and forbidden changes.
- **`cleanup`**: how you will restore the original app state after the run.
- **`max_steps`**: the model decision limit, from 1 to 50. Notes, rejected decisions and stopping decisions count too. The template uses 10.
- **`allow_toggle_changes`**: leave `false` unless your investigation permits tapping controls recognized as toggles. Other taps can still change state.
- **`sandbox_confirmed`**: set `true` after confirming the selected account, server and devices are isolated and safe to modify. It records your confirmation; it does not create or verify isolation. Keep it `false` when isolation is unknown or the resources are shared/production.

The template starts unconfirmed. Prose boundaries do not enforce isolation.
## Explore sliders

Exploration supports tap, scroll and Back by default. To experiment with sliders,
add this `allowed_actions` field to your working brief:

```json
"allowed_actions": ["tap", "scroll_forward", "scroll_backward", "press_back", "drag_slider"]
```

1. Describe what you want to learn in `objective` and permit slider changes in `boundaries`.
2. Keep `allow_toggle_changes` false for a slider-only investigation.
3. Run the same exploration test with your edited brief.
4. Review the before/after screenshots and XML. The explorer records visible effects and remaining questions.

`drag_slider` performs one short drag between positions on the selected slider,
even when Appium exposes no numeric value. For example, 80 → 60 describes a
leftward gesture, not a verified volume change. Each drag spans 1–30 percentage
points and has no automatic retries. Returning the thumb to an estimated position
does not prove exact restoration.

For an **exact numeric target**, explicitly allow `set_slider_value` instead.
That method reads and verifies the resulting value; it stops for guidance when
the value is unavailable. [Action details](../reference/appium-actions.md)
explain both methods.

The [Home Assistant slider brief](../app/homeassistant/sliders.json) permits
experimental drags on its isolated demo players. Its native sliders currently
expose no numeric value through Appium.

## Another investigation in the same app

1. Create a different brief file, such as `runs/app/demo-app/another-investigation.json`.
2. Keep `app_slug` and `app_package` for the same app.
3. Change `investigation_slug`, `objective`, `boundaries` and `cleanup` for the new investigation.
4. Prepare its starting state and confirm isolation.
5. Run [workflow step 6](../README.md#6-t1--run-exploration) with `--exploration-brief runs/app/demo-app/another-investigation.json`. The argument is the path to the file you created in step 1.

The filename selects the input. `investigation_slug` groups the results.
Each execution creates a new run folder, including reruns of the same brief.

## Optional brief fields

- `starting_state` can describe your prepared screen; it does not perform setup or verify a precondition.
- `references` can supply requirement excerpts for the model; it does not fetch URLs. Without requirements, proposed criteria remain hypotheses.
- `allowed_actions` selects permitted tools. The default is `tap`, `scroll_forward`, `scroll_backward`, `press_back`; both slider tools require explicit inclusion.
