# Home Assistant exploration demo

An Android emulator and isolated Home Assistant demo server are the current worked example—not a requirement baked into the exploration runtime. Commands below target macOS and assume you are in the cloned repository. Replace the example AVD name and device serial with yours.

## Local configuration

| Item | Value |
| --- | --- |
| Repository | `.` |
| Python environment | `.venv` inside that repository |
| Android SDK | `$HOME/Library/Android/sdk` |
| AVD name | `Pixel_10_Pro` |
| Emulator serial | `emulator-5554` |
| Appium address | `http://127.0.0.1:4725` |
| Docker container | `home-assistant-test` |
| Home Assistant configuration | `$HOME/home-assistant-test/config` |
| Server address on Mac | `http://localhost:8123` |
| Server address in emulator app | `http://10.0.2.2:8123` |
| Android package | `io.homeassistant.companion.android` |
| Launch activity | `.launch.LaunchActivity` |

The project has been exercised with these example settings; verify your own installation. If a tool or
environment is missing, use [one-time setup](../../prerequisites.md) first.

Use three terminals:
- **Terminal A:** preparation, then pytest commands.
- **Terminal B:** emulator process, if it is not already running.
- **Terminal C:** Appium server logs.

## First-time demo server setup

Complete [project installation](../../prerequisites.md) first. Docker Desktop is
only needed for this example. Use a dedicated server with simulated entities;
do not connect real household devices.

If `home-assistant-test` already exists, reuse it and skip creation.
Otherwise, create a configuration directory outside the repository:

```sh
mkdir -p "$HOME/home-assistant-test/config"
```

In that directory create `configuration.yaml` with:

```yaml
default_config:
demo:
```

The [official demo integration](https://www.home-assistant.io/integrations/demo/)
provides simulated entities. This local container example publishes only port
8123 on localhost; it is not a production smart-home deployment. See the
[official installation documentation](https://www.home-assistant.io/installation/alternative/)
for supported deployment options.

```sh
docker run -d --name home-assistant-test \
  -p 127.0.0.1:8123:8123 \
  -v "$HOME/home-assistant-test/config:/config" \
  ghcr.io/home-assistant/home-assistant:2026.10.2
```

This is an example version pin, not a claim that this exact image was validated
in every environment. Finish onboarding at `http://localhost:8123`, using demo
credentials. Install the Home Assistant Android companion app, connect it to
`http://10.0.2.2:8123`, and sign in. Confirm Overview and demo players are visible.

## 1. Start Docker and Home Assistant

In Terminal A:

```sh
cd "$(git rev-parse --show-toplevel)"
open -a Docker
docker info
```

If Docker is still starting, wait for Docker Desktop to report it is running,
then repeat `docker info`. Continue only when that succeeds.

```sh
docker start home-assistant-test
docker ps --filter name=home-assistant-test --format '{{.Names}}  {{.Status}}  {{.Ports}}'
curl -sS -o /dev/null -w 'Home Assistant HTTP %{http_code}\n' --max-time 10 http://localhost:8123
open http://localhost:8123
```

Expected: running container, port `127.0.0.1:8123->8123/tcp`, HTTP `200`,
and the Home Assistant page. If startup is incomplete, wait and repeat the curl
check. Do not recreate the container or redo onboarding.

## 2. Start or reuse the emulator

In Terminal A, make SDK commands available for this terminal:

```sh
export ANDROID_HOME=$HOME/Library/Android/sdk
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
adb devices
```

If `emulator-5554 device` is already listed, **do not start another emulator**.

Otherwise, in Terminal B:

```sh
$HOME/Library/Android/sdk/emulator/emulator -avd Pixel_10_Pro -port 5554
```

Leave Terminal B open. In Terminal A, after the emulator window has booted:

```sh
adb devices
adb -s emulator-5554 shell getprop sys.boot_completed
```

Expected: `emulator-5554 device` and boot value `1`. Unlock the emulator.
If another device uses port 5554, resolve that conflict rather than starting a
second instance on the same port.

## 3. Open and check the app

In Terminal A:

```sh
adb -s emulator-5554 shell pm path io.homeassistant.companion.android
adb -s emulator-5554 shell cmd package resolve-activity --brief io.homeassistant.companion.android
adb -s emulator-5554 shell am start -n io.homeassistant.companion.android/.launch.LaunchActivity
```

Expected: installed APK path and activity
`io.homeassistant.companion.android/.launch.LaunchActivity`.
If no APK is found, install Home Assistant from the emulator's Play Store first.

In the app, ensure **Home Assistant URL** is **`http://10.0.2.2:8123`**.
`127.0.0.1` inside the emulator means the emulator, not the Mac.
This runbook does not require ADB reverse forwarding.

Log in manually if needed. Confirm Overview loads and demo media players exist.
Use only this isolated demo server, never real household devices.
Record the initial playback state so you can restore it after exploration.

## 4. Start Appium explicitly

In Terminal C:

```sh
cd "$(git rev-parse --show-toplevel)"
npm run appium:drivers
curl -fsS --max-time 5 http://127.0.0.1:4725/status
```

Expected driver: `uiautomator2@8.7.0`.
If curl cannot connect, start the server:

```sh
npm run appium:start
```

Leave Terminal C open. This command stays running and prints server logs.
Use **`npm run appium:start`**, not a global `appium` command.

If curl already reports `"ready":true`, reuse that server; do not start a second
one. If it was started outside this project and lacks the driver, stop it in its
own terminal and start the project server above.

Back in Terminal A:

```sh
curl -fsS --max-time 5 http://127.0.0.1:4725/status
```

Continue when ready is true. All commands below explicitly use port 4725.

**Alternative only:** you may omit manual startup and let pytest start its local
server. Pytest stops servers it starts, but leaves an existing manual server
running. Automatic server logs go under `runs/appium-server/`.

## 5. Activate Python and load Gemini credentials

In Terminal A:

```sh
cd "$(git rev-parse --show-toplevel)"
source .venv/bin/activate
python -c 'import sys; print(sys.executable)'
python -m pip check
```

Expected Python: `./.venv/bin/python`.

For paid exploration, check that the key file exists:

```sh
test -f .env && echo ".env exists"
```

If it does not print that message, complete the
[key-file setup](../../prerequisites.md#4-create-the-gemini-key-file-once).
Do not proceed with a missing or empty file.

Load the file and check only whether the key is present:

```sh
set -a
source .env
set +a
if test -n "$GEMINI_API_KEY"; then
  echo "Gemini key loaded"
else
  echo "STOP: fill in GEMINI_API_KEY in .env"
fi
```

Never print the key itself. Loading it does not send a model request.
A new terminal needs these activation/export steps again.

## 6. Review the brief and run exploration

The existing brief is
[home-assistant-media-player.json](../../workflow/examples/home-assistant-media-player.json).

Inspect it in Terminal A:

```sh
python -m json.tool docs/workflow/examples/home-assistant-media-player.json
python -c 'from pathlib import Path; from agentic_mobile_test.agent.exploration import ExplorationBrief; b = ExplorationBrief.load(Path("docs/workflow/examples/home-assistant-media-player.json")); print("Valid brief; decision limit:", b.max_steps)'
```

These checks are offline. Review the objective, boundaries, cleanup and sandbox
confirmation. No locator list, assertion JSON or new test module is required.

The framework automatically loads its reusable instruction from
`src/agentic_mobile_test/prompts/exploration.md`. Do not paste that instruction
into your brief. Edit the brief for app-specific objectives; change the packaged
instruction only when intentionally changing the agent's general behavior.
Each run saves the exact instruction as `system-prompt.md` and records its SHA-256
under `prompt` in `exploration.json`. A running planner keeps its initial snapshot.
After exploration stops, the runtime attempts one separately budgeted final review
using the original brief, stop reason, action records, screenshots and compact XML.
This happens even after exploration budget exhaustion, provided evidence exists.
The reviewer reports fulfilled work, gaps and a recommended next step for your
decision. It never automatically resumes exploration. No new assertion template
is needed. Review judgments are still model assessments.

**The next command makes paid Gemini requests and can change demo playback:**

```sh
python -m pytest tests/autotests/ui/exploration/test_exploratory_app.py \
  --run-gemini \
  --exploration-brief docs/workflow/examples/home-assistant-media-player.json \
  --appium-server-url http://127.0.0.1:4725 \
  --appium-udid emulator-5554 \
  --appium-package io.homeassistant.companion.android \
  --appium-activity '.launch.LaunchActivity' \
  --appium-no-reset -q
```

Each backslash must be the last character on its line. Do not paste a trailing
space after it. Run only one device test/exploration at a time.

The example permits **15 decisions**, including notes/reviews/finish, not 15
guaranteed taps. The runner sets **600 maximum output tokens per response** and
an **estimated $0.02 exploration cost ceiling**. Final review reserves a separate
**one call, 1000 output tokens and $0.02**, for a **$0.04 combined estimated ceiling**.
Provider retries are disabled. Exploration can stop
earlier. These are local controls, not a provider billing cap or a wall-clock
deadline.

`--appium-no-reset` preserves app data/login; it does not restore playback or
other state after a run. Appium may relaunch/foreground the app.

## 7. Find and review the report

The terminal prints an absolute path ending in `exploration.json`.
To locate the most recently created report:

```sh
python -c 'from pathlib import Path; reports = sorted(Path("runs/exploration").glob("*/exploration.json")); print(reports[-1].resolve() if reports else "No exploration report found")'
```

Open the newest run folder in Finder:

```sh
python -c 'from pathlib import Path; import subprocess; reports = sorted(Path("runs/exploration").glob("*/exploration.json")); subprocess.run(["open", str(reports[-1].parent.resolve())], check=True) if reports else print("No exploration report found")'
```

Read `report.md`, then review `exploration.json`, `actions.jsonl`, and
`screens/<number>/screenshot.png` plus `hierarchy.xml`.
`system-prompt.md` records the reusable instructions used for this run.

- **completed:** separate completion review accepted the evidence; not a product pass or coverage proof.
- **blocked / needs_guidance / budget_exhausted:** partial evidence, pytest skip.
- **error:** harness/execution error, pytest failure.
- **review_unavailable:** final review could not be obtained; inspect saved evidence
  and the recorded error manually. No retry or automatic continuation occurs.

Newest does not mean successful. Prefer the exact printed path when selecting a
particular run. Evidence may contain private UI data; do not commit it.

**Manually restore the player's original playback state and return to Overview.**
The current explorer does not perform or verify cleanup automatically.

## 8. Turn evidence into a pytest test

Give your coding assistant this, replacing only the report path:

```text
Repository: your cloned agentic-mobile-test repository
Exploration report: <paste the absolute exploration.json path printed by pytest>

Read AGENTS.md and docs/workflow/README.md.
Verify the report's evidence hashes and inspect its recorded actions/screens.
Separate exercised behavior from assumptions and untested claims.
Use the supported evidence to author a deterministic pytest candidate under
tests/autotests/ui/home_assistant/.
Put setup and cleanup in local fixtures; keep actions/assertions in the test.
Use existing AppiumActions/device helpers. Do not change their contracts.
Do not require Gemini or exploration files during replay.
Validate imports and pytest collection without live execution. Report prerequisites, uncertainty and the exact live
replay command for me to run.
```

There is **no generator CLI** to invoke. The coding assistant authors the candidate.
Review expected results before live execution. An observed behavior is not
automatically the intended product behavior.

## 9. End the session

1. Restore any state changed by exploration.
2. Wait for pytest to finish. If you interrupted it, inspect the partial report
   and restore state manually.
3. Stop the manually started Appium server with Ctrl+C in Terminal C.
4. Close the emulator window if finished.
5. Optional: stop the Home Assistant server without deleting its data:

```sh
docker stop home-assistant-test
```

In Terminal A:

```sh
unset GEMINI_API_KEY
deactivate
```

Do not delete the container, config directory, or emulator data.

## 10. Troubleshooting

| Symptom | Check or action |
| --- | --- |
| npm reports ENOENT / missing package.json | Run `cd "$(git rev-parse --show-toplevel)"` first. |
| `appium: command not found` | Use `npm run appium:start`; no global Appium is required. |
| Missing project Appium | Run `npm ci` in the repo; this reinstalls local Node dependencies. |
| Missing UiAutomator2 | Check `npm run appium:drivers`; if absent, run `npm run appium:setup`, then restart Appium. |
| Port already in use | Check `curl http://127.0.0.1:4725/status` and `lsof -nP -iTCP:4725 -sTCP:LISTEN`; reuse the correct server or stop it in its owning terminal. Do not blindly kill processes. |
| Missing .venv or Python packages | Complete one-time Python setup, then activate .venv. |
| Missing .env or empty key | Complete one-time key setup. Never print or paste credentials. |
| App opens but cannot connect | Mac curl check must succeed; emulator app URL must be `http://10.0.2.2:8123`. |
| Docker container missing | Inspect `docker ps -a`; stop and recover the existing setup, do not create a blank replacement blindly. |
| Home Assistant not ready | Run `docker logs --tail 50 home-assistant-test`; inspect locally and redact before sharing. |
| Emulator missing/offline | Check `adb devices`, boot value and the emulator window before pytest. |
| App/activity missing | Repeat step 3; do not guess a different activity. |
| Exploration is skipped | Include `--run-gemini`, the brief, and the device/app arguments. |
| 429 / quota / billing error | Stop; inspect provider usage. Do not loop paid runs or add retries. |
| Policy rejects a target | Inspect the rejected attempt and XML. Do not weaken policy merely to force a pass. |

## New objectives and current limits

For a new Home Assistant objective, copy the existing brief without overwriting it:

```sh
cd "$(git rev-parse --show-toplevel)"
cp -n docs/workflow/examples/home-assistant-media-player.json docs/workflow/examples/home-assistant-next.json
open -e docs/workflow/examples/home-assistant-next.json
```

Edit objective, boundaries and cleanup. Keep the same package. Substitute
`home-assistant-next.json` in the exploration command. The copy retains
`sandbox_confirmed: true`; reconfirm isolation before running.

For a different app, change package/activity and use its isolated environment.
A runtime tool gap may still require implementation; a new brief cannot add tools.

Current limits: one candidate per run, tap/scroll/back tools, no automatic
restoration or backend verification, no visual-coordinate fallback. The model
receives current screenshot plus accumulated XML/action history. Boundaries in
prose are not complete safety enforcement. Broader investigation and automatic
handoff validation are not implemented. Completion reviews and missing-evidence
feedback are recorded under `completion_reviews` in exploration.json and report.md.
`completion-prompt.md` captures the review instruction. Budget exhaustion leaves a
partial report, even if the explorer requested finish.
