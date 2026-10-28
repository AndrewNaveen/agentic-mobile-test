# Appium installation and troubleshooting

[Workflow](../README.md)

Complete [system tool installation](installation.md#install-system-tools) first.
For daily emulator and server startup, follow the [workflow](../README.md#1-t1--open-your-working-terminal).
Commands use `$HOME/repos/agentic-mobile-test` and the default Android SDK path.

## One-time installation

```sh
cd "$HOME/repos/agentic-mobile-test"
npm ci
npm run appium:drivers
```

If UiAutomator2 is missing, install it:

```sh
npm run appium:setup
```

Check the installation:

```sh
npm run appium:doctor
```

The project pins Appium 3.7.0 and UiAutomator2 8.7.0. Doctor should report
zero required fixes. For failures, see [Troubleshooting](#troubleshooting).

## Troubleshooting

- **Missing driver:** run `npm run appium:setup`, then restart Appium.
- **Missing AVD:** list available names with `"$HOME/Library/Android/sdk/emulator/emulator" -list-avds`.
- **Port 4725 occupied:** check `/status` and `lsof -nP -iTCP:4725 -sTCP:LISTEN`. Reuse the project server or stop it in its owning terminal.
- **Device/session error:** verify the device serial, app package and launch activity in your pytest command.
- **SDK or Java error:** check the paths below and rerun `npm run appium:doctor`.

## Optional: custom SDK and Java paths

Defaults are `$HOME/Library/Android/sdk` for the SDK and
`/Applications/Android Studio.app/Contents/jbr/Contents/Home` for Java.
If yours differ, set `ANDROID_HOME`, `ANDROID_SDK_ROOT` and/or `JAVA_HOME` in each
terminal before Appium commands, and replace the SDK path in the emulator command.
`JAVA_HOME` must contain `bin/java`.
