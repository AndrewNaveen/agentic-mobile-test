# Agentic test architecture

The project owns the reasoning and assurance loop. Appium remains the
low-level actuator.

```text
Scenario
  type + goal + preconditions + allowed actions + test-data refs
  + assertions + cleanup expectation + step budget
                              │
                              ▼
                        AgentLoop
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
      AppiumObserver    StructuredPlanner    Verifier
   screenshot + UI XML    model gateway    fixed assertions
              │               │                │
              └──── observed element refs ─────┘
                              │
                              ▼
                        ActionPolicy
               allowlist, target, data, budget,
                    ineffective-repeat checks
                              │
                              ▼
                       AppiumExecutor
                              │
                              ▼
                        AppiumActions
                              │
                              ▼
                       app and device
```

## Trust boundary

The planner receives the goal, success criteria, screenshot, a compact list of
observed elements, available test-data names, recent outcomes, and remaining
step budget. It returns one structured action such as:

```json
{
  "action": "tap",
  "target_ref": "e003",
  "reason": "The About phone row matches the requested destination",
  "expected_effect": "The device information screen opens"
}
```

The planner cannot submit coordinates, Appium selectors, arbitrary Python,
assertions, test-data values, or retry loops. `ActionPolicy` rejects actions
outside the approved scenario. `AppiumExecutor` resolves the opaque element
reference and calls an existing `AppiumActions` operation.
For `launch_app`, the scenario supplies a named app allowlist and the executor
passes only its mapped app ID to the shared `device.apps` facade.

The verifier runs independently from the planner. A successful tap means only
that Appium executed an interaction; it never proves the business assertion.

## Observation and grounding

`AppiumObserver` captures a screenshot and UI hierarchy. It assigns temporary
references to elements and deterministically prepares a locator only when a
unique accessibility id, resource id, or text value is available. The model
sees the reference and semantic attributes, not the locator.

Visual coordinate grounding is deliberately excluded from the first slice. It
requires its own reviewed confidence, bounds, evidence, and fallback policy.

## Temporary references and durable targets

Observed references such as `e003` exist for one captured screen and are the
only targets exposed to the runtime planner. They are not saved as regression
locators. A promoted deterministic test instead names a durable semantic target
such as `settings.about_device`.

`TargetCatalog` loads those app-specific definitions from a strict,
version-controlled JSON file. Each target contains ranked, complete Appium
locators. `AppiumTargetResolver` queries them in order and accepts a candidate
only when exactly one element satisfies the requested `present`, `visible`, or
`clickable` state. It then returns the reviewed Appium locator to the existing
`AppiumActions` operation.

The resolver writes one JSON object per decision to `locator-trace.jsonl`.
Records include the target and screen, source catalog, current package and
activity, every attempted locator, total and eligible match counts, selected
rank, and elapsed time. A failed resolution also captures screenshot and UI XML
before raising `LocatorResolutionError`; pytest therefore records a test
failure rather than a false product failure.

## Outcomes

- **Passed:** every approved assertion was observed.
- **Product failure:** a verifier has affirmative evidence of incorrect product behavior.
- **Test failure:** planning, grounding, policy, execution, or verification could not produce a trustworthy result.
- **Blocked:** a required external resource or precondition was unavailable.

Every attempt may write a redacted scenario, JSONL step trace, screenshots, UI
source, and final result under `runs/`.

## Scenario intake and discovery output

Settings scenarios are strict, versioned JSON files under
`tests/autotests/ui/android_settings/scenarios/`. The classification is
`positive`, `negative`,
or `edge`; it describes the engineer's test intent but does not change the
verifier or let the planner alter the expected result. Preconditions, cleanup
expectations, action permissions, assertions, and step limits are part of the
reviewed contract.

The UI-level `tests/autotests/ui/conftest.py` provides the
`android_settings_environment` pytest fixture. It uses the existing
`MobileDevice.settings.launch_root()` operation before the test and again in
teardown. It verifies the Settings package and stores checkpoint screenshots,
UI XML, and lifecycle metadata. The fixture is test lifecycle code; it does not
add another device abstraction.

After a passed run, `evidence.RunArtifacts` writes `discovered-path.json` with a
stable schema: scenario metadata, semantic actions, observed target metadata and
locator candidate, before/after evidence paths and hashes, transition
fingerprints, and final independent verification. Failed or blocked runs keep
their normal result evidence but do not produce a successful-path candidate.
The record is explicitly marked for human review before deterministic
regression-code generation.

The offline test generator validates this record and its referenced evidence,
then emits a deterministic pytest candidate using durable semantic target ids.
It never copies temporary observation references or raw observed locators into
the generated test. The `.py.candidate` output is not collected until a human
reviews and promotes it.

## Device facade

The device layer composes platform differences instead of inheriting UI actions:

```text
MobileDevice
├── profile   platform, model, OS version, session identifier
├── geometry  current window, orientation, pixel ratio, viewport
├── settings  AndroidDeviceAdapter or IOSDeviceAdapter
├── apps      installed-app checks and foreground launch
├── network   connectivity read/set and Airplane mode
├── ui        durable semantic target operations
└── actions   existing deterministic AppiumActions
```

`DeviceProfile` reads capabilities without a hard-coded list of models or OS
versions. `DeviceGeometry` is read on demand, so a rotation or a different
screen size does not leave cached coordinates. Android and iOS adapters expose
the same reviewed intent, such as launching the system Settings root, while
each performs only the platform-specific Appium command needed for that intent.

Shared app operations live at `device.apps`: check installation before launch,
activate the package/bundle id, and wait until it is foregrounded. A missing app
raises `AppNotInstalledError` with available failure evidence. Network controls
live at `device.network`; the Android adapter reads/writes connectivity through
Appium's Android connectivity extension and verifies the resulting state. The
iOS adapter reports radio control as unsupported rather than silently falling
back to UI tapping. Capture `device.network.get_connectivity()` before changing
device radios and restore that exact `DeviceConnectivity` in fixture teardown;
Airplane mode can also affect Wi-Fi and mobile data. These reusable operations
belong in `src/agentic_mobile_test/device/`; app-specific targets and scenario
setup remain under their UI test feature directory.

This layer does not decide test intent, locate application-specific controls,
or determine a verdict. A pytest scenario or approved agent action supplies a
semantic target; `SemanticUI` resolves it from a version-controlled catalog;
`AppiumActions` performs the interaction; and the scenario verifies the result.
The Android Settings journey exercises this composition on a real session.
The iOS adapter is contract-tested with a fake until an iOS Appium environment
is configured.
