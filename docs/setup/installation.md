# First-time installation

[Workflow](../README.md)

These steps cover macOS and Android. Commands use
`$HOME/repos/agentic-mobile-test`; substitute your checkout path if different.

## Install system tools

You need Git, Python 3.11, Node.js, npm and Android Studio. Appium requires
Node `^20.19.0 || ^22.12.0 || >=24.0.0` and npm 10 or newer.

With Homebrew installed, install the tools you are missing:

```sh
brew install git python@3.11 node
brew install --cask android-studio
```

Alternatively, use the installers for [Git](https://git-scm.com/downloads/mac),
[Python](https://www.python.org/downloads/macos/), [Node.js](https://nodejs.org/en/download)
and [Android Studio](https://developer.android.com/studio).

In Android Studio:

1. Finish the setup wizard.
2. In **SDK Manager**, install Platform-Tools, Android Emulator and a Google Play system image compatible with your Mac.
3. In **Device Manager**, create an Android Virtual Device (AVD) named `Pixel_10_Pro`, or use your existing demo AVD.

The workflow uses the default SDK location, `$HOME/Library/Android/sdk`.

## Clone the repository

For a new checkout:

```sh
cd "$HOME"
mkdir -p "$HOME/repos"
cd "$HOME/repos"
git clone https://github.com/AndrewNaveen/agentic-mobile-test.git
cd "$HOME/repos/agentic-mobile-test"
```

For an existing checkout, use `cd "$HOME/repos/agentic-mobile-test"`.

## Install Python dependencies

```sh
cd "$HOME/repos/agentic-mobile-test"
test -d .venv || python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,appium,gemini]'
python -m pip check
python -m pytest --collect-only -q -p no:cacheprovider
```

Expected: no dependency errors and two collected tests: exploration and Home Assistant playback.
Collection does not execute the test.

## Install Appium

Complete [Appium installation](appium.md#one-time-installation), then continue below.

## Create a Gemini key file

### 1. Copy your API key

Open [Google AI Studio's API Keys page](https://aistudio.google.com/apikey)
and sign in. Copy an existing Gemini API key, or use **Create API key** to create
one and copy it. If you already have the key, continue below.

### 2. Open the project's `.env` file

Run these commands in T1. They create `.env` if needed and open it in TextEdit:

```sh
cd "$HOME/repos/agentic-mobile-test"
test -f .env || cp .env.example .env
chmod 600 .env
open -e .env
```

### 3. Paste the key into the file and save

In **TextEdit**, find this line:

```text
GEMINI_API_KEY=
```

Paste your copied key immediately after `=` on that same line:

```text
GEMINI_API_KEY=PASTE_YOUR_ACTUAL_KEY_HERE
```

Replace `PASTE_YOUR_ACTUAL_KEY_HERE` with the key you copied. This line belongs
in `.env`, in the project root beside `pyproject.toml`. Press **Cmd+S** to save.

### 4. Load the saved key into T1

Return to T1 and run:

```sh
set -a
source .env
set +a
```

Python can now read `GEMINI_API_KEY` in this terminal. Repeat this loading step
whenever you open a new T1; workflow step 1 includes it. `.env` is ignored by Git.

Next: [workflow step 1 — open your working terminal](../README.md#1-t1--open-your-working-terminal).
For SDK, Java or driver problems, see [Appium troubleshooting](appium.md#troubleshooting).
