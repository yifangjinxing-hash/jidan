# Changelog

## Unreleased — initial public preview

- Opened the JGraph capability runtime, policy gate, durable grant ledger, receipt chain, and Android AppFunctions adapter under Apache-2.0.
- Added a controlled Android 17 memo provider for write, readback, and idempotency experiments.
- Added UTF-8-safe Windows/ADB transport and multilingual Unicode regression tests.
- Added the language-neutral `memo:` semantic entry point and a BCP 47 locale hint boundary.
- Extracted the Android UI into localized resources, added RTL-safe display, and seeded 23 locales.
- Added security reporting, contribution guidance, and locale validation.
- Added fail-closed Android semantic-surface routing and a verified WeChat text-share handoff that stops at the native recipient picker.
- Added the MCP-compatible JCL 0.1 `message.compose` profile with Android, iOS, and Web plan bindings plus a verified Android/WeChat wrapper.
- Added host-owned no-send outcome semantics, recipient-hint isolation, and adapter false-success regression tests.
- Added the compile-only JCL Pinyin Frontend 0.1 with NFC normalization, explicit tone/boundary rules, hashed aliases, fail-closed homophone handling, and verbatim payload preservation.
- Added a primary-source history audit and route guardrails: freeze JCL's observable contract and conformance vectors, keep JGraph host-internal, preserve platform-native bindings, and treat natural language as untrusted input rather than executable authority.
- Updated the public `message.compose` demo and README examples to pass through TaskPlan, Grant, confirmation, Runtime, and Receipt instead of presenting direct Registry invocation as the product path.
- Hardened `message.compose` so generic/community bindings can report only `handoff_planned`, recursively reject nested adapter-authored outcome claims, and require an explicit demo-only flag before simulated approval.
- Rebuilt the project landing pages with a local hero illustration, architecture visualization, capability status table, and multilingual README entry points.
