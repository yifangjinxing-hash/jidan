# Languages and internationalization

Jidan is designed so language is data at the edge, not part of the trusted machine protocol.

## Project documentation languages

| Language | Entry point | Review status |
|---|---|---|
| English | [README](../../README.md) | Source |
| 简体中文 | [README.zh-CN](../../README.zh-CN.md) | Seed |
| 繁體中文 | [README.zh-TW](../../README.zh-TW.md) | Machine-assisted seed |
| 日本語 | [README.ja](../../README.ja.md) | Machine-assisted seed |
| Español | [README.es](../../README.es.md) | Machine-assisted seed |

Localized READMEs are maintained as welcoming entry points. The English README and machine-readable capability profiles remain the canonical technical references when translations differ. Fluent review is welcome through the [translation issue template](../../.github/ISSUE_TEMPLATE/translation.yml).

## Three separate guarantees

1. **Unicode transport:** memo text in any writing system can pass through JSON, the task graph, ADB, AppFunctions, storage, readback, and the UI without transliteration or implicit normalization.
2. **Localized UI:** Android strings use resource qualifiers and BCP 47 locale configuration. Unknown locales fall back to the complete English resource set.
3. **Semantic understanding:** the bundled `memo: <content>` prefix is language-neutral. The offline Chinese rule parser is one optional adapter. Free-form understanding in another language requires a reviewed parser or constrained multilingual-model adapter; it must still emit the same stable semantic action.

These guarantees are deliberately not conflated. Shipping an interface translation does not mean a language has a safe natural-language parser, and accepting Unicode does not mean every phrase is understood.

## Seed UI language packs

The first public version contains complete resource-key sets for these 23 locales. “Seed” means mechanically validated and open for fluent-speaker review.

| BCP 47 | Language | Android resource | Status |
|---|---|---|---|
| `en` | English | `values/` | Source |
| `ar` | العربية | `values-ar/` | Seed |
| `bn` | বাংলা | `values-bn/` | Seed |
| `de` | Deutsch | `values-de/` | Seed |
| `es` | Español | `values-es/` | Seed |
| `fil` | Filipino | `values-fil/` | Seed |
| `fr` | Français | `values-fr/` | Seed |
| `hi` | हिन्दी | `values-hi/` | Seed |
| `id` | Bahasa Indonesia | `values-in/` | Seed |
| `it` | Italiano | `values-it/` | Seed |
| `ja` | 日本語 | `values-ja/` | Seed |
| `ko` | 한국어 | `values-ko/` | Seed |
| `nl` | Nederlands | `values-nl/` | Seed |
| `pl` | Polski | `values-pl/` | Seed |
| `pt-BR` | Português (Brasil) | `values-pt-rBR/` | Seed |
| `ru` | Русский | `values-ru/` | Seed |
| `sw` | Kiswahili | `values-sw/` | Seed |
| `th` | ไทย | `values-th/` | Seed |
| `tr` | Türkçe | `values-tr/` | Seed |
| `uk` | Українська | `values-uk/` | Seed |
| `vi` | Tiếng Việt | `values-vi/` | Seed |
| `zh-CN` | 简体中文 | `values-zh-rCN/` | Seed |
| `zh-TW` | 繁體中文 | `values-zh-rTW/` | Seed |

Arabic exercises right-to-left layout. Bengali, Devanagari, Han, kana, Hangul, Cyrillic, Thai, Latin diacritics, emoji, apostrophes, and shell metacharacters are represented in automated transport tests.

## Add any language

1. Choose the correct BCP 47 tag and Android resource qualifier.
2. Copy `reference-app/app/src/main/res/values/strings.xml` to the new `values-*` directory.
3. Translate human-facing values only. Keep every resource key and `%1$s` / `%1$d` placeholder unchanged.
4. Add the BCP 47 tag to `reference-app/app/src/main/res/xml/locales_config.xml`.
5. Run:

   ```text
   python prototype/tools/check_locales.py
   ```

6. Test truncation, font fallback, RTL direction where relevant, and mixed-script user content on Android.
7. State whether the wording was native-reviewed, fluent-reviewed, or machine-assisted in the pull request.

## Never translate protocol fields

The following remain stable ASCII contracts:

- semantic intent IDs such as `memo.create`;
- capability and function IDs;
- JSON schema property names;
- `status`, effect, scope, grant, nonce, hash, and receipt fields;
- package names, operation IDs, and memo IDs.

Human-facing explanations may be localized around those values. Changing the values themselves would break signatures, policies, idempotency, or interoperability.
