# Android App Track (MVP Started)

This folder now contains a minimal native Android project (Kotlin) to start the APK track.

Current MVP scope:

- Setup screen for webhook URL, API key, and source label
- Local persistence of settings with SharedPreferences
- "Send test" button to POST a sample SMS payload to your server

Planned next:

- SMS capture receiver
- Background queue + retries
- Signed request support
- Optional headless worker mode

## Project Structure

- `app/` Android module
- `build.gradle.kts` root Gradle file
- `settings.gradle.kts` Gradle settings

## Build & Run

1. Open this folder (`phone_module/app`) in Android Studio.
2. Let Gradle sync complete.
3. Run the `app` configuration on an Android device/emulator.

## Server Compatibility

The test sender posts to your existing endpoint:

- `POST /sms`
- Header: `X-API-Key` (if configured)
- Body: `{ "sms": "...", "source": "android-app" }`

This matches your current backend in `pesa_logger/webhook.py`.
