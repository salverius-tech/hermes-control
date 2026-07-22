# Disposable Device Sandbox

This fixture supports **local-only, deterministic** physical-device checks without touching a real Hermes profile, repository, API database, or credential.

It is intentionally **not** part of `scripts/verify.py`: that verifier must remain usable with an empty device and without a connected phone.

## What `prepare` creates

Below the one new directory passed to `--root`, the tool creates:

- an isolated native Hermes-style `projects.db` and `state.db`;
- one project with a workspace and an empty `repo/` folder;
- one session;
- three fixed work threads: attention-required, running, and completed;
- an isolated Control API SQLite database and fixed fixture-only token;
- `.hermes-control-device-sandbox`, which is required before `destroy` will delete anything.

The server always binds to `127.0.0.1`. Use `adb reverse` for a USB-connected Android device; do not expose this fixture on a LAN or configure real credentials.

## P6.2/P6.3 populated Inbox and project-detail review

From the repository root, use a previously unused directory:

```bash
python scripts/device_sandbox.py prepare --root .device-sandbox
python scripts/device_sandbox.py serve --root .device-sandbox --port 18787
```

In a second terminal, map the device loopback port and run Maestro with the identifiers printed by `prepare`:

```bash
adb reverse tcp:18787 tcp:18787
maestro test \
  -e PROJECT_ID=sandbox-mobile-project \
  -e P6_ATTENTION_ROOT=sandbox-attention-root \
  -e P6_ACTIVE_ROOT=sandbox-active-root \
  -e P6_RECENT_ROOT=sandbox-recent-root \
  .maestro/p6-inbox-project-detail.yaml
```

Before that flow, save these fixture-only settings in the installed app:

- Control API URL: `http://127.0.0.1:18787`
- API token: `sandbox-device-token`

The flow asserts stable Inbox section/thread selectors and the project detail order: attention, active, recent, sessions, then workspace/repository management.

## P7.5 task-submission slice

With the same loopback server and reverse mapping:

```bash
maestro test \
  -e API_URL=http://127.0.0.1:18787 \
  -e DEVICE_TOKEN=sandbox-device-token \
  -e PROJECT_ID=sandbox-mobile-project \
  .maestro/p7-device-task.yaml
```

This flow clears only the app's local state, saves fixture settings, chooses the deterministic native project, submits a task, and asserts task detail navigation. The fixture has no real Hermes executor, so it is suitable for API/mobile submission behavior only—not proof of real task execution or completion.

## Cleanup

Stop the `serve` process first, then remove the device reverse mapping and fixture:

```bash
adb reverse --remove tcp:18787
python scripts/device_sandbox.py destroy --root .device-sandbox
```

`destroy` refuses unmarked directories. It never accepts a request to delete a normal project directory.

## Deliberately not covered / P7.5 status

This tooling makes the P6.2/P6.3 populated-state visual/device flow and the P7.5 native-project task-submission slice repeatable. It does **not** complete P7.5. Still requiring device scenarios and purpose-built fixtures are workspace creation, repository clone, real executor task completion, retry/continuation, WebSocket reconnect, offline queue behavior, and recovery-plan confirmation.
