# Installation (macOS / Android)

Start in your cloned repository. These instructions cover the macOS development setup; other operating systems have not been validated end-to-end. Reuse existing working installations.

```sh
git clone https://github.com/AndrewNaveen/agentic-mobile-test.git
cd agentic-mobile-test
```

For daily use, follow the [workflow](workflow/README.md).

## 1. Check installed system tools

```sh
cd "$(git rev-parse --show-toplevel)"
python3.11 --version
node --version
npm --version
ls -d "/Applications/Android Studio.app"
$HOME/Library/Android/sdk/emulator/emulator -list-avds
```

Previously exercised: Python 3.11.4, Node 26.9.0, npm 11.19.1, AVD Pixel_10_Pro.
The installed Appium package declares Node `^20.19.0 || ^22.12.0 || >=24.0.0`
and npm `>=10`.

If tools are missing, install only the missing items. With Homebrew already installed:

```sh
brew install python@3.11 node
brew install --cask android-studio
```

These commands change system software; they are not daily startup commands.
Launch Android Studio, complete SDK installation, then use SDK Manager to install
Android SDK Platform-Tools, Android Emulator and an Android system image.
In Device Manager create a Pixel AVD if none exists. Existing local AVD:
`Pixel_10_Pro`. Docker is optional and needed only for the Home Assistant example.

For each terminal using adb:

```sh
export ANDROID_HOME=$HOME/Library/Android/sdk
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
adb version
```

The project Appium wrapper selects Android Studio's bundled Java automatically
unless JAVA_HOME is already set. Its expected path is:

```sh
"/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin/java" -version
```

## 2. Install Python dependencies

Create the environment **only if .venv does not exist**:

```sh
cd "$(git rev-parse --show-toplevel)"
test -d .venv || python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,appium,gemini]'
python -m pip check
python -m pytest --collect-only -q -p no:cacheprovider
```

Collection does not start Docker, an emulator, Appium or a model request.
Do not use a global pytest executable; `python -m pytest` uses the activated Python.

## 3. Install project-local Appium and its Android driver

```sh
cd "$(git rev-parse --show-toplevel)"
npm ci
npm run appium:drivers
```

If UiAutomator2 is absent:

```sh
npm run appium:setup
```

Then verify:

```sh
npm run appium:drivers
npm run appium:doctor
```

Pinned server: Appium 3.7.0. Driver: UiAutomator2 8.7.0.
Both use this project's `.appium-home`, not a global driver directory.
Fix required doctor checks before running tests. Do not reinstall an already
installed driver every session.

## 4. Create the Gemini key file once

Obtain a Gemini API key for your selected Google AI Studio project. Confirm that
project's billing and spending controls before paid experiments. Model selection
comes from the request configuration, not a billing dashboard filter.

Create the file without overwriting an existing one:

```sh
cd "$(git rev-parse --show-toplevel)"
test -f .env || cp .env.example .env
chmod 600 .env
open -e .env
```

In the editor, set `GEMINI_API_KEY=your_actual_key` and save. Do not paste the key
into chat, commit it, or use a command that prints it. Verify Git ignores the file:

```sh
git check-ignore .env
```

Expected output: `.env`. Load it in each terminal before paid exploration:

```sh
set -a
source .env
set +a
test -n "$GEMINI_API_KEY" && echo "Gemini key loaded"
```
The framework does not automatically load .env.

Use the session runbook to make an explicitly enabled exploration run.
See [gateway reference](model-gateway.md) for limits.

## 5. Choose your investigation

Use the [general workflow](workflow/README.md), or the separate
[Home Assistant demo guide](examples/home-assistant/README.md) for Docker,
server onboarding, app setup and the exact exploration command.
