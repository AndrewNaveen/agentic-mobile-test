# Discovery to deterministic regression

The live agentic test records a successful path in `runs/<run-id>/discovered-path.json`.
That record is evidence for authoring, not executable test code. Review the
screenshots, UI snapshots, target decisions, and fixed assertion results before
generating a candidate.

From the repository root, run:

```sh
python -m agentic_mobile_test.generation \
  runs/<run-id> \
  --scenario tests/autotests/ui/android_settings/scenarios/youtube_airplane_mode_offline.json
```

The generator checks that the run passed, the scenario contract is unchanged,
each action is allowed, every referenced screenshot/UI snapshot matches its
recorded SHA-256, and target references resolve to reviewed semantic targets.
An approved `launch_app` step is replayed through `device.apps` using its
scenario-defined `launchable_apps` reference; the model never supplies a package
ID directly.
When a recorded locator does not match exactly one target in
`tests/autotests/ui/android_settings/targets/android_settings.json`, provide an
explicit reviewed mapping:

```json
{
  "schema_version": 1,
  "step_targets": {
    "2": "settings.about_device"
  }
}
```

Pass it with `--target-map path/to/target-map.json`. Keys are 1-based discovery
step numbers. The generator writes a `.py.candidate` beside the scenario; pytest
does not collect that suffix. It uses semantic `device.ui` operations and the
same deterministic scenario assertions, never ephemeral observation IDs or raw
locators.

Review each action, precondition, cleanup, target, and oracle. Confirm that the
test starts from the intended state and that it cannot pass without performing
the required behavior. Then rename the file to `.py`, run that exact test on the
configured emulator, and review its evidence. Generated code is a draft, not an
approved regression until an engineer has verified it.
