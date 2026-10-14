# First-Time Prerequisites

Complete this page once per machine. For the commands to repeat at the start
of each session, use [Working with the project](workflow/README.md).

> Important: run every `npm` and `pytest` command from the repository root.
> They use this project's `package.json`, lockfile, Python environment, and
> configuration. If your shell prompt shows `~`, first run `cd` to the repo.

```sh
cd /Users/andrewsekar/repos/agentic-mobile-test
```

## 1. Install system tools

Install Python 3.11+, Node.js, Android Studio, and Android SDK Platform-Tools.
In Android Studio's SDK Manager, install the Android SDK Platform and Android
Emulator. Create and start an Android virtual device. Verify it is visible:

```sh
adb devices
```

On macOS, the default SDK and Java paths used by this project are:

- Android SDK: `$HOME/Library/Android/sdk`
- Java: `/Applications/Android Studio.app/Contents/jbr/Contents/Home`

If your installation differs, set `ANDROID_HOME` and `JAVA_HOME` in your shell
before running Appium. Ensure `adb`, `node`, and `npm` are on `PATH`.

## 2. Install Python dependencies

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,appium,gemini]'
pytest
```

The Gemini SDK is installed here, but tests still do not call Gemini unless you
explicitly opt in with `--run-gemini`.

## 3. Install the project-local Appium server

Do not install or invoke a global `appium` command. From the repository root:

```sh
npm ci
npm run appium:setup
npm run appium:doctor
```

`npm ci` installs the pinned Appium server from `package-lock.json`.
`appium:setup` installs the pinned UiAutomator2 driver under `.appium-home`,
and `appium:doctor` checks Android driver prerequisites. These commands must
run inside the project. Running them from your home directory (`mac:~`) caused
the pasted `ENOENT` errors because npm could not find this repo's
`package.json` or lockfile.

## 4. Set up Gemini once (optional; paid API)

1. Create a Gemini API key in Google AI Studio and enable billing for its
   project. Keep prepaid auto-reload off; billing dashboards and spend limits
   can take time to update.
2. Create a local key file from the safe template:

   ```sh
   test -f .env || cp .env.example .env
   ```

   Edit `.env` and set `GEMINI_API_KEY=your_key_here`. `.env` is ignored by
   Git. Never commit, print, or paste the key into chat or logs. The framework
   only uses the key when a Gemini test is explicitly enabled.
3. The request model and per-run call/token/cost limits are configured in the
   gateway and test. The billing page's model selector only filters reports; it
   does not set the model used by the code.

To use a different key-storage method, export `GEMINI_API_KEY` directly in the
terminal running pytest. See the workflow guide for the safe per-session export
command and current experiment limits.

## 5. Start Appium manually (optional)

The pytest fixture can start and stop the local Appium server automatically.
For visible server logs or debugging, check the default port first:

```sh
curl -fsS http://127.0.0.1:4725/status
```

If it is not already ready, run this from the repository root and leave that
terminal open:

```sh
cd /Users/andrewsekar/repos/agentic-mobile-test
npm run appium:start
```

This starts the project's local Appium on `http://127.0.0.1:4725`; run pytest
from a second terminal in the repository. Pytest reuses the server. Do not try
to start a second copy on the same port. The `npm run appium:start` command
fails from `~` because npm searches the current directory for `package.json`.
