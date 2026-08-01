# Jidan

**A small, multilingual Android agent runtime built around capabilities, task graphs, explicit approval, and receipts.**

[简体中文](README.zh-CN.md) · [Languages and translation](docs/i18n/README.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

> Experimental prototype. Jidan is not a replacement Android distribution, a privilege-escalation tool, or a production assistant. Use only controlled apps, test devices, and disposable data.

## Why Jidan

Modern phones make simple goals travel through heavy apps, pages, ads, and incompatible silos. Jidan explores a smaller unit of software:

```text
user goal
  → semantic action
  → capability contract
  → task graph
  → policy and confirmation
  → adapter execution
  → verifiable receipt
```

The planner is treated as untrusted. A capability is invoked only when its schema, scope, effect, grant, and confirmation requirements all pass.

## What is included

- `prototype/` — a dependency-free Python capability kernel, policy gate, task-graph runtime, persistent grant ledger, hash-chained receipts, Android AppFunctions adapter, and read-only semantic-surface router.
- `reference-app/` — a controlled Android 17 memo provider exposing `putMemo`, `getMemoState`, and `getStoreStats` AppFunctions.
- `docs/` — architecture notes, Android research, roadmap material, and the internationalization guide.
- 73 unit tests covering policy, schema validation, replay rejection, Unicode transport, multilingual memo input, Android command construction, and fail-closed semantic routing.

Generated APKs, emulator images, SDKs, raw device logs, receipts, screenshots, and SQLite ledgers are deliberately not published in Git.

## Languages

Jidan separates human language from machine protocol:

- Memo content accepts and preserves arbitrary Unicode.
- `memo: <content>` is a language-neutral command that works with content in any writing system.
- The deterministic Chinese command parser remains as one replaceable offline adapter.
- Intent IDs, capability IDs, schema properties, status values, grants, and receipts stay stable and are never translated.
- The Android reference UI follows the system locale, supports right-to-left layout, and ships seed translations for 23 locales. Unsupported locales safely fall back to English.
- Any BCP 47 language can be added without changing the runtime contract.

Seed translations are a starting point, not a claim of native-speaker review. Fluent review and additional language packs are welcome.

## Quick start

Run the local runtime tests with Python 3.11 or newer:

```bash
cd prototype
python -m unittest discover -s tests
python appfunctions_smoke.py
```

Validate every Android language pack:

```bash
python prototype/tools/check_locales.py
```

Build the controlled Android app with JDK 17+ and Android SDK 37:

```bash
cd reference-app
./gradlew :app:assembleDebug
```

On Windows, use `gradlew.bat`. Do not pipe natural-language text through the default Windows PowerShell 5.1 native pipeline; see the UTF-8 note in [the prototype guide](prototype/README.md#windows-unicode-arguments).

## Safety boundary

The repository does not include Shizuku, root integration, Accessibility automation, arbitrary shell execution, or a general third-party app controller. Real external actions remain confirmation-gated. The Android app is a deliberately controlled reference target.

The current local SQLite grant ledger provides at-most-once authorization while the same database remains intact. It is not a hardware-backed security boundary and does not promise exactly-once task execution after a crash.

## Project status

The useful result today is a working experimental loop—not a finished operating system:

- capability discovery and conservative registration;
- preflight with zero partial execution before approval;
- schema-bound task grants and persistent replay rejection;
- controlled AppFunctions writes with exact readback and provider idempotency;
- UTF-8-safe host-to-device transport;
- globally extensible UI and semantic-action boundaries.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and translation contributions.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
