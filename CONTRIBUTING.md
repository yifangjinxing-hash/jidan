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

## License

By submitting a contribution, you agree that it is licensed under the repository's Apache License 2.0.
