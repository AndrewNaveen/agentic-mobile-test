# Prerequisites

The deterministic architecture checks require only Python. Live Android runs
also require Node.js, Android Studio, and an emulator or connected device.

## Python environment

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,appium]'
pytest
```

## Android tooling

Install Android Studio using its standard setup and ensure it provides:

- Android SDK
- Android SDK Platform-Tools
- Android Emulator

If the tools are not already on `PATH`, configure Bash:

```sh
export ANDROID_HOME="$HOME/Library/Android/sdk"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
```

Create and start a stable Android virtual device in Android Studio, then verify
the connection:

```sh
adb devices
```

## Project-local Appium

Do not install Appium globally. Install the pinned server and UiAutomator2
driver inside this repository:

```sh
npm ci
npm run appium:setup
npm run appium:doctor
```

Pytest starts and stops this server automatically for tests that request the
`driver` fixture. Manual startup remains available for debugging:

```sh
npm run appium:start
```

The real model gateway is intentionally absent. Its SDK, environment variable,
and setup instructions will be added only after the provider is selected.
