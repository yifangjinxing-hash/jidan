# Jidan Reference Memo

Mobile experience shells:

- [`shell/`](shell/README.md): installable Android shell and Android front-door adapters.
- [`ios-shell/`](ios-shell/README.md): SwiftUI shell, Apple Speech input, direct low-risk navigation, and remote iPhone Simulator evidence.

This is a deliberately narrow Android 17 reference provider used to prove real AppFunctions writes, exact readback, two layers of replay protection, and Jidan receipt integrity.

The visible UI follows the system locale, supports right-to-left layout, and ships complete seed resources for 23 locales. User memo content is wrapped with first-strong bidirectional isolation and stored without implicit Unicode normalization. Translation keys and format placeholders are checked by `../prototype/tools/check_locales.py`.

It uses the official AndroidX AppFunctions `1.0.0-alpha10` `@AppFunctionServiceEntryPoint` architecture and exposes:

- `BaseMemoAppFunctionService#putMemo(operationId, memoId, content)`;
- `BaseMemoAppFunctionService#getMemoState(memoId)`;
- `BaseMemoAppFunctionService#getStoreStats()`.

`putMemo` persists data with synchronous `SharedPreferences.commit()` inside a process lock. A new idempotency key increments `physicalMutationCount`; an exact retry increments `putInvocationCount` but returns `replayed` without another mutation; reusing a key with a different payload throws `AppFunctionInvalidArgumentException`. The operation ledger persists the original content and assigned revision, so replaying an old operation after later writes or a process restart returns that operation's immutable snapshot without rolling back the current memo.

Build with Android SDK 37. The checked Gradle Wrapper pins Gradle 9.6.1 and its SHA-256 digest:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
.\gradlew.bat --no-daemon :app:assembleDebug
.\gradlew.bat --no-daemon :app:lintDebug
```

Install on the controlled emulator:

```powershell
& "$env:ANDROID_HOME\platform-tools\adb.exe" -s emulator-5554 install -r -t .\app\build\outputs\apk\debug\app-debug.apk
```

The companion `../prototype/reference_app_validation.py` performs the 30-round acceptance suite and validates returned JSON rather than trusting process exit codes. It requires reviewed absolute paths, an exact device serial, unique receipt/event/summary paths, a new persistent `--grant-ledger` path, and an explicit `--approve`. The final run recreates the Jidan Runtime against the same durable grant ledger, force-stops and restarts the provider, replays round 1 after round 30, rejects an idempotency-key collision, and verifies both evidence hash chains plus the SQLite ledger.

Official implementation guidance: <https://developer.android.com/ai/appfunctions/add-appfunctions>
