<p align="center">
  <img src="docs/assets/jidan-hero.png" alt="Jidan connects one AI intent to interchangeable device bindings while a human keeps the final action" width="100%" />
</p>

<h1 align="center">Jidan</h1>

<p align="center">
  <strong>An open, capability-first runtime for AI actions across apps and devices.</strong><br />
  One intent contract. Replaceable platform bindings. Human control at the commit point.
</p>

<p align="center">
  <a href="#-quick-start"><img src="https://img.shields.io/badge/Quick_Start-195A41?style=for-the-badge" alt="Quick start" /></a>
  <a href="profiles/message.compose.tool.json"><img src="https://img.shields.io/badge/JCL_Profile-0.1-2F8F68?style=for-the-badge" alt="JCL Profile 0.1" /></a>
  <a href="docs/07-universal-game-spike-zh.md"><img src="https://img.shields.io/badge/Nine_Lights-Conformance_Spike-6E5AA8?style=for-the-badge" alt="Nine Lights conformance spike" /></a>
  <a href="docs/i18n/README.md"><img src="https://img.shields.io/badge/UI_Locales-23-D9A441?style=for-the-badge" alt="23 seed UI locales" /></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/Contributions-Welcome-3978C6?style=for-the-badge" alt="Contributions welcome" /></a>
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.zh-TW.md">繁體中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a>
</p>

> [!IMPORTANT]
> Jidan is an experimental prototype, not a replacement Android distribution, a privilege-escalation tool, or a production assistant. Use controlled apps, test devices, and disposable data.

## ✨ Why Jidan

Mobile software is still organized around app silos. A simple goal crosses pages, ads, permissions, and incompatible platform APIs. Jidan explores a smaller unit of software: a **capability contract** that an untrusted planner can propose but only a deterministic host can authorize and execute.

```text
human goal → semantic action → capability contract → policy gate
           → selected adapter → observed handoff receipt → human commit
                                                        (outside current send verification)
```

The long-term target is not “one more super app.” It is a thin, open compatibility layer where Android, Apple, Web, HarmonyOS, Windows, and future hosts can implement the same stable intent semantics.

> **Share semantics, not implementations.** Natural language and UI inputs remain outside the JCL machine contract; Kotlin, Swift, JavaScript, and C/C++ remain Host or adapter choices. Web bindings still live inside the browser sandbox. The Pinyin 0.1 input experiment is frozen, not the project substrate. See the [historical design lessons and route guardrails](docs/06-history-lessons-and-route-guardrails-zh.md) (Chinese).

## 🔌 One contract, many bindings

[`message.compose`](profiles/message.compose.tool.json) is the first Jidan Capability Layer (JCL) profile. JCL 0.1's first public serialization uses an MCP-compatible Tool profile; JCL itself is neither a new programming language nor tied to one transport or session model.

```python
from jidan.models import Step, TaskPlan

# The caller proposes a capability, not a platform or an adapter call.
plan = TaskPlan(
    id="compose-demo",
    goal="prepare a message draft",
    steps=(Step(
        id="compose",
        capability="message.compose",
        arguments={"content": "See you at three."},
    ),),
)
# A trusted Host validates, grants, confirms, selects a binding, executes,
# and writes the receipt. See prototype/message_compose_demo.py.
```

| Stable contract | Replaceable binding | Current proof |
|---|---|---|
| `message.compose` | Android Intent | Data-only plan; verified WeChat handoff available |
| `message.compose` | Apple Shortcut / Share Sheet | Data-only plan |
| `message.compose` | Web editable draft | Data-only plan |
| `message.compose` | Community adapter | Locally registered; no central publication whitelist |

Every result is explicit about reality:

```json
{
  "state": "handoff_planned",
  "delivery": {
    "attempted": false,
    "sent": false,
    "verified": false
  },
  "nextAction": "user_review_and_send"
}
```

`handoff_planned` never masquerades as an opened UI. A verified Android picker reports `handoff_opened`, but delivery still remains `sent: false` because Jidan never chooses the recipient or presses Send.

### Nine Lights: a small interoperability check

<p align="center">
  <img src="docs/assets/ninelights-icon.png" alt="Nine Lights 3 by 3 puzzle icon" width="180" />
</p>

[`game.ninelights.start`](profiles/game.ninelights.start.tool.json) and
[`game.ninelights.press`](profiles/game.ninelights.press.tool.json) describe a
deterministic 3 × 3 lights puzzle. The Python CLI sends every action through
TaskPlan, a minimal READ Grant, `JidanRuntime`, and hash-chained Receipts. A
separate JavaScript Web Host implements the same Profiles and is checked against
the same [conformance vectors](profiles/conformance/game.ninelights.vectors.json).
After cloning the repository, open the dependency-free
[Nine Lights Web UI](prototype/web/ninelights.html) directly in a browser; no
build step is required.

Windows users can also launch the Chinese desktop UI or build a single-file EXE
with its own icon:

```powershell
cd prototype
python -m pip install PyInstaller==6.21.0
python ninelights_gui.py
powershell -NoProfile -File tools/build_ninelights_exe.ps1 -Python python
```

The output is `prototype/build/pyinstaller/dist/JidanNineLights.exe`. Local
development builds are unsigned. Do not bypass Windows SmartScreen: run only an
EXE you built from a trusted checkout, and compare its SHA-256 with the value
printed by the build script. If local policy blocks scripts, inspect the script
and use your organization's approved execution process.

This demonstrates shared observable semantics, not a shared Runtime, a general
game language, or Android/iOS support. See the [scope and evidence note](docs/07-universal-game-spike-zh.md) (Chinese).

> [!NOTE]
> The Pinyin Frontend 0.1 experiment was frozen on 2026-08-02. Its code, Profile,
> demo, and tests remain for compatibility and reproduction, but it is no longer
> an active route or quick-start feature. New syntax and aliases are out of scope.

## 🧭 Architecture

```mermaid
flowchart LR
    H["Human goal"] --> P["Untrusted proposal source<br/>AI planner · UI input"]
    P --> C["Stable capability<br/>message.compose"]
    C --> G{"Deterministic gate<br/>schema · scope · grant · confirmation"}
    G --> R["Host-selected binding"]
    R --> A["Android"]
    R --> I["Apple"]
    R --> W["Web"]
    R --> N["New platform"]
    A --> M["Native mobile review surface"]
    I --> M
    W --> E["Editable Web review surface"]
    N --> S["Binding-specific review surface"]
    M --> Q["Observed handoff receipt<br/>sent = false"]
    E --> Q
    S --> Q
    M --> X["Human final action<br/>outside current send verification"]
    E --> X
    S --> X
    G --> L["Grant ledger"]

    classDef core fill:#195A41,color:#F2F8F5,stroke:#2F8F68,stroke-width:2px;
    classDef human fill:#F5E7BF,color:#3B2A00,stroke:#D9A441;
    class C,G,R,Q core;
    class H,X human;
```

## ✅ What works today

| Layer | Status | Evidence |
|---|---:|---|
| Capability registry and schema validation | ✅ | Dependency-free Python prototype |
| Task graphs, scoped grants, confirmation gate | ✅ | Deterministic preflight and execution |
| Durable replay rejection | ✅ | SQLite grant ledger |
| Hash-chained execution receipts | ✅ | Runtime receipt log |
| Capability-definition authorization | ✅ | Grants pin Schema, effect, and adapter identity |
| Discovery error taxonomy | ✅ | Pure classifier + unit tests; real connection/fallback integration is pending |
| Android 17 AppFunctions | ✅ | Controlled reference provider and live harness |
| Semantic-surface discovery | ✅ | AppFunctions → RemoteInput → shortcut → public share |
| Verified WeChat native handoff | ✅ | Exact picker activity; no recipient selection or Send |
| Cross-platform `message.compose` profile | 🧪 | Android / iOS / Web plans; Android verified binding |
| Nine Lights semantics spike | 🧪 | Python Runtime/Receipts + independent JS Host; shared vectors |
| Pinyin Frontend 0.1 | ⏸️ | Frozen compatibility experiment; no new syntax or aliases |
| Production-grade mobile agent OS | 🗺️ | Not claimed yet |

## 🛡️ Safety by construction

- **The planner is not the security boundary.** Model output is validated as untrusted data.
- **Open publication is not blind execution.** Anyone may implement an adapter; each device still owns local trust, installation, policy, and isolation.
- **Recipient hints are not authority.** `message.compose.recipient` is never passed to a platform binding.
- **Input frontends are not authority.** Language or UI input cannot grant, execute, select a platform, or rewrite approved payload data.
- **Adapters cannot declare success.** Delivery state is generated by the host, not copied from third-party adapter output.
- **Authorization binds more than a name.** A Grant pins the effective capability definition; changed Schema, effect, or adapter identity requires a new Grant.
- **Ambiguous effects are not retried as success.** Unknown outcomes remain unknown and are receipted conservatively.
- **The user keeps the last word.** Send, pay, delete, and security-changing actions require an explicit commit boundary.

Read [SECURITY.md](SECURITY.md) before connecting a real device.

## 🚀 Quick start

Run the full dependency-free prototype test suite with Python 3.11+:

```bash
cd prototype
python -m unittest discover -s tests -p "test_*.py"
python message_compose_demo.py
python ninelights_gui.py --self-test
python ninelights_demo.py --level cross --moves 5
node tools/check_ninelights_web.js
python appfunctions_smoke.py
```

The message demo stops at `awaiting_confirmation` by default. Its
`--simulate-approval` option is labeled as a simulation and is not evidence of
a user's confirmation. Nine Lights is a local READ/COMPUTE demo and requires no
confirmation; its Python path still uses the full Runtime and Receipt chain.

Validate all Android language packs:

```bash
python prototype/tools/check_locales.py
```

Build the controlled Android reference app with JDK 17+ and Android SDK 37:

```bash
cd reference-app
./gradlew :app:assembleDebug
```

On Windows, use `gradlew.bat`. For PowerShell 5.1 Unicode caveats, see the [prototype guide](prototype/README.md#windows-unicode-arguments).

## 🗂️ Repository map

```text
profiles/       MCP-compatible JCL capabilities and conformance vectors
prototype/      capability kernel, adapters, policy, grants, receipts, demos
reference-app/  controlled Android 17 AppFunctions provider
docs/           architecture, research, roadmap, internationalization
```

Generated APKs, emulator images, raw device logs, screenshots, receipts, and SQLite ledgers are deliberately excluded from Git.

## 🌍 Language without protocol fragmentation

Jidan separates human language from machine protocol:

- arbitrary Unicode content survives JSON, task graphs, ADB, storage, readback, and UI;
- the Android reference UI ships **23 seed locale packs**, including RTL Arabic;
- `memo: <content>` is a language-neutral deterministic entry point;
- the frozen `zh-Latn-pinyin` experiment remains available only for compatibility and reproducibility;
- capability IDs, schema fields, grants, hashes, and receipt values remain stable ASCII contracts;
- new UI translations and reviewed language adapters do not require a protocol fork.

Seed translations are an open-source starting point, not a claim of native review. See [Languages and internationalization](docs/i18n/README.md) to improve one.

## 🤝 Build with us

Useful contributions include:

- a new `message.compose` platform binding;
- a conformance fixture that catches false-success behavior;
- native review for one of the 23 seed locale packs;
- a constrained language adapter that emits existing semantic IDs;
- an independent Nine Lights Host that passes the shared vectors without importing the Python Runtime;
- reproducible tests against a controlled app or device.

Start with [CONTRIBUTING.md](CONTRIBUTING.md), the [90-day roadmap](docs/04-90-day-execution-roadmap-zh.md), and the [seven-day protocol review](docs/08-seven-day-protocol-review-zh.md) (Chinese).

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
