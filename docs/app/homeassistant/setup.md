# Home Assistant setup

[Workflow — prepare your app](../../README.md#3-t1--prepare-and-select-your-app)

Use this at **workflow step 3**, with the emulator running and T1 open
in the project. It prepares the demo server and Android app for exploration.

## 1. Start the demo server

Open Docker Desktop. For an existing `home-assistant-test` container, run in T1:

```sh
docker start home-assistant-test
```

If you have not created this container, complete
[first-time demo server setup](#first-time-demo-server-setup) below instead.

Open [Home Assistant in your browser](http://localhost:8123) and sign in with
your demo account. Wait for the dashboard and simulated media players to appear.

## 2. Connect the Android app

1. Open Home Assistant Companion on the emulator. Install it from the emulator's Play Store if needed.
2. Connect to **`http://10.0.2.2:8123`**. This is the Android emulator's address for the server on your Mac.
3. Sign in with the same demo account you used in the browser.
4. Finish onboarding and permission dialogs. Leave **Overview** visible with the demo players accessible.
5. Note the players' current playback states for cleanup.

If the app is already signed in to this demo server, open Overview.

## 3. Return to the workflow

Continue to [workflow step 4 — start Appium](../../README.md#4-t3--start-appium).
Then step 5 creates your editable brief and step 6 runs it using its full file path.

## First-time demo server setup

Install and open [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/).
In T1, create the dedicated demo server:

```sh
mkdir -p "$HOME/home-assistant-test/config"
test -f "$HOME/home-assistant-test/config/configuration.yaml" ||
  printf 'default_config:\ndemo:\n' > "$HOME/home-assistant-test/config/configuration.yaml"
docker run -d --name home-assistant-test \
  -p 127.0.0.1:8123:8123 \
  -v "$HOME/home-assistant-test/config:/config" \
  ghcr.io/home-assistant/home-assistant:2026.10.2
```

`default_config:` enables standard features; `demo:` adds simulated entities.
The server is exposed on localhost and keeps its data in
`$HOME/home-assistant-test/config`.

Open [Home Assistant](http://localhost:8123), finish onboarding with a dedicated
demo account and skip real-device integrations. Then
[connect the Android app](#2-connect-the-android-app).

## Stop the demo server

After restoring app state, run in T1:

```sh
docker stop home-assistant-test
```

The container and its data remain available for your next session.
