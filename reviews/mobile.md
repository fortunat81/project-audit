# Review checklist: mobile apps (trait `mobile`: Expo, React Native, Flutter, native)

## Always (quick and full)
- **Secrets in the app bundle:** anything in the app (code, `app.json` `extra`, `EXPO_PUBLIC_*`, Dart constants, `--dart-define` values) can be extracted from the installed app. Paid API keys and admin keys must move behind a server function. Cross-check `exposed-keys.txt`.
- **Tokens on the device:** auth tokens must be in secure storage (`expo-secure-store`, `react-native-keychain`, `flutter_secure_storage`, Keychain/Keystore), not AsyncStorage, SharedPreferences or plain files.

## Full mode
- **Permissions:** compare permissions requested (`app.json` `android.permissions`, `ios.infoPlist` usage strings, `AndroidManifest.xml`, `Info.plist`) with what the code uses. Unused permissions (microphone, location, contacts) get apps rejected and scare users. Each iOS usage string must explain the real reason.
- **Network:** cleartext HTTP allowed (`usesCleartextTraffic`, `NSAllowsArbitraryLoads`) in production builds.
- **Android backups:** `allowBackup` enabled for apps holding sensitive data.
- **iOS privacy manifest:** apps using required-reason APIs (UserDefaults/AsyncStorage, file timestamps, disk space, boot time) need `PrivacyInfo.xcprivacy` entries (Expo: `ios.privacyManifests` in `app.json`); missing ones can get the app rejected.
- **Deep links:** routes opened by links that act without confirmation (e.g. `myapp://pay?amount=`).
- **WebViews:** loading arbitrary URLs, or JavaScript bridges exposed to remote pages.
- **Logging:** `console.log`/`print` of tokens or personal data left in release builds.
- **Expo:** `expo-doctor.txt` results; OTA update channel and runtime version set so updates can't reach incompatible builds.
