# Contributing to Jidan

Thank you for helping build a smaller, calmer Android agent runtime.

## Start here

1. Fork the repository and create a focused branch.
2. Run the Python tests from `prototype/`:

   ```text
   python -m unittest discover -s tests
   ```

3. For Android changes, build the controlled reference app from `reference-app/`:

   ```text
   ./gradlew :app:assembleDebug
   ```

4. Never commit APKs, Android SDK files, emulator images, receipts, SQLite ledgers, device dumps, tokens, or absolute user paths.
5. Explain side effects and validation clearly in the pull request.

## Translation contributions

Jidan uses Android resource qualifiers and BCP 47 language tags. Human-facing text may be translated; protocol identifiers such as `memo.create`, capability IDs, schema property names, status values, and receipt fields must remain stable.

To add or improve a language:

1. Copy `reference-app/app/src/main/res/values/strings.xml` into the correct localized `values-*` directory.
2. Preserve every resource name and formatting placeholder exactly.
3. Add the locale to `reference-app/app/src/main/res/xml/locales_config.xml` when it is new.
4. Run `python prototype/tools/check_locales.py`.
5. Have a fluent speaker review meaning, tone, plural forms, and right-to-left layout when applicable.

Translations can be partial during review, but merged locale files must pass the key and placeholder checks. See [the language guide](docs/i18n/README.md).

## Semantic-language adapters

Natural-language parsers are adapters at the untrusted edge. A parser may accept any language, but it must return the stable semantic action contract, reject ambiguity, preserve the original user text, and never grant or execute a capability directly. Task planning, policy checks, confirmation, execution, and receipts remain separate stages.

The Pinyin Frontend 0.1 experiment was frozen on **2026-08-02**. Its code,
profile, demo, and tests remain for compatibility and reproducibility. Security
fixes and regressions that preserve the frozen behavior are welcome; new
syntax, aliases, fuzzy matching, capability mappings, or active product entry
points are not. See the [frozen design note](docs/05-jcl-pinyin-frontend-zh.md).

## Conformance spikes

Nine Lights tests semantic portability rather than shared implementation. A
change to `game.ninelights.start` or `game.ninelights.press` must:

1. keep platform and UI fields out of the public Profile;
2. preserve stateless, deterministic state transitions and fail-closed invalid-state handling;
3. update shared vectors only when the public contract is intentionally versioned;
4. run both the Python tests and `node prototype/tools/check_ninelights_web.js`;
5. state separately which Host uses `JidanRuntime` and which implements the contract independently.

Passing the same vectors does not justify claims about Android, iOS, a shared
Runtime, or a general-purpose game language. See the
[Nine Lights evidence boundary](docs/07-universal-game-spike-zh.md).

## Capability bindings

New platform bindings do not need a central Jidan publication whitelist. They do need a focused implementation, local installation trust, and conformance evidence before a host enables them.

For `message.compose` bindings:

1. Keep the public capability ID, input schema, and output schema unchanged.
2. Treat `recipient` only as a display hint; the runtime intentionally does not pass it to adapter code.
3. Return a platform binding plan only. Do not author `delivery`, `sent`, `state`, `riskLevel`, `executionMode`, or other host-owned outcome fields at any nesting depth.
4. Report a data-only integration as `handoff_planned`. Use `handoff_opened` only through a verifier-backed wrapper that proves the expected user-controlled review surface is actually open; the generic/community binding API cannot select this state.
5. Never select a recipient or issue the final Send action.
6. Add regression tests for malformed input, false-success output, and exception handling.

The first profile lives at [`profiles/message.compose.tool.json`](profiles/message.compose.tool.json), and the reference binding API is in [`prototype/jidan/message_compose.py`](prototype/jidan/message_compose.py).

## License

By submitting a contribution, you agree that it is licensed under the repository's Apache License 2.0.
