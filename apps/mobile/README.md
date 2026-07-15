# Hermes Mobile App

Expo React Native app for Android-first Hermes monitoring and task creation.

## Setup

```bash
pnpm install
pnpm run typecheck
pnpm start
```

## Screens

- Dashboard: high-level local Hermes control center.
- Bottom navigation: primary route bar for Home, Tasks, New, Projects, and API.
- Tasks: reads queued/running/completed/failed tasks from the companion API.
- Projects: reads project summary counts from the companion API.
- New Task: submits typed or voice-dictated prompts to the companion API.
- Settings: stores companion API URL and token using secure storage.

## Device testing

For an Android emulator, `http://127.0.0.1:8787` may work depending on networking. For a physical Android device, use the Windows host LAN IP or Tailscale hostname, for example:

```text
http://192.168.1.50:8787
```

Voice transcription uses `expo-speech-recognition`, so Android review builds must be regenerated after native dependency or plugin changes and installed as release APKs for Metro-free phone review.

## More detail

- App/backend architecture: `../../ARCHITECTURE.md`
- API contract: `../../docs/API.md`
- Testing strategy: `../../TESTING.md`
- Operations and Android troubleshooting: `../../docs/OPERATIONS.md`
