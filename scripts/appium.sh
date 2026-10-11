#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_ANDROID_HOME="$HOME/Library/Android/sdk"
ANDROID_STUDIO_JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"

export APPIUM_HOME="$PROJECT_ROOT/.appium-home"
export ANDROID_HOME="${ANDROID_HOME:-$DEFAULT_ANDROID_HOME}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"

if [[ -z "${JAVA_HOME:-}" ]]; then
  export JAVA_HOME="$ANDROID_STUDIO_JAVA_HOME"
fi

if [[ ! -x "$ANDROID_HOME/platform-tools/adb" ]]; then
  echo "Android platform-tools were not found under $ANDROID_HOME" >&2
  exit 1
fi

if [[ ! -x "$JAVA_HOME/bin/java" ]]; then
  echo "Java was not found under $JAVA_HOME" >&2
  exit 1
fi

if [[ ! -x "$PROJECT_ROOT/node_modules/.bin/appium" ]]; then
  echo "Project Appium is missing. Run: npm install" >&2
  exit 1
fi

export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$JAVA_HOME/bin:$PATH"

exec "$PROJECT_ROOT/node_modules/.bin/appium" "$@"
