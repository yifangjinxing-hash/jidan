# Changelog

## Unreleased — initial public preview

- Reframed the landing pages around **real micro-actions first**: reduce one concrete step, disclose the observed state, and stop before the human commit instead of leading with an app catalogue or a universal-agent claim.
- Added a controlled Alipay front-door Lab adapter with an empty input contract, exact package/version/certificate/component pins, host-side APK signature verification, explicit launch, stable Activity/Window foreground evidence, and payment outcome fields fixed to false. It is not automatic payment or an ordinary-user Binding, and `opened` must never be confused with `paid`. See [the product and protocol note](docs/09-alipay-micro-actions-and-protocol-lessons-zh.md).
- Raised dynamically discovered AppFunctions with no reviewed effect contract from `external` to the fail-closed `irreversible` ceiling; fixed adapters may narrow risk only through their own signed capability definition and tests.
- Made file-backed ReceiptLog appends atomic across cooperating local processes by locking, rereading and verifying the disk tail, flushing each append, and exercising an eight-process race regression.
- Moved Nine Lights out of homepage badges and the product quick start into a clearly labeled Conformance Lab. Its Profiles, shared vectors, Web/desktop surfaces, build script, and tests remain available as developer fixtures.
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
- Froze the Pinyin Frontend 0.1 experiment on 2026-08-02: retained its compatibility surface and regression coverage while removing it from the active route and quick start; new syntax and aliases are out of scope.
- Added the offline Nine Lights Conformance Lab fixture with stateless `game.ninelights.start` / `game.ninelights.press` Profiles and shared vectors. The Python CLI uses the full Runtime and Receipt path; the independent JavaScript Web Host tests the same observable semantics without claiming a shared Runtime, a user product, or mobile support.
- Added a primary-source history audit and route guardrails: freeze JCL's observable contract and conformance vectors, keep JGraph host-internal, preserve platform-native bindings, and treat natural language as untrusted input rather than executable authority.
- Updated the public `message.compose` demo and README examples to pass through TaskPlan, Grant, confirmation, Runtime, and Receipt instead of presenting direct Registry invocation as the product path.
- Hardened `message.compose` so generic/community bindings can report only `handoff_planned`, recursively reject nested adapter-authored outcome claims, and require an explicit demo-only flag before simulated approval.
- Rebuilt the project landing pages with a local hero illustration, architecture visualization, capability status table, and multilingual README entry points.
- Added a native Chinese Nine Lights desktop UI, reproducible one-file Windows build, headless packaged self-test, and generated PNG/ICO artwork as Conformance Lab artifacts rather than product releases.
- Made capability-definition digests mandatory in newly issued Grants, intentionally invalidated pre-digest Grants, rejected same-name definition drift before adapter invocation, prevented in-place handler replacement, and recorded the effective digest in every Receipt.
- Added transport-neutral discovery error classification so authentication, unsupported discovery, call-scoped JSON-RPC errors, malformed protocol responses, and transport failures cannot collapse into one misleading state.
- Added a strict 2026-07-27—2026-08-02 protocol/community review and revised the 90-day route around stateless requests, versioned platform adapters, explicit parameter support, verifiable commit stages, and opaque asset handles.
