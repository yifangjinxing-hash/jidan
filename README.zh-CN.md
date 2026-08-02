<p align="center">
  <img src="docs/assets/jidan-hero.png" alt="Jidan 把一个 AI 意图连接到可替换的多端 Binding，同时把最后动作留给人" width="100%" />
</p>

<h1 align="center">Jidan</h1>

<p align="center">
  <strong>面向 App 与设备的开放式 AI 能力运行时。</strong><br />
  一份意图契约，多种平台 Binding，现实动作的最后一步仍由人决定。
</p>

<p align="center">
  <a href="#-快速开始"><img src="https://img.shields.io/badge/快速开始-195A41?style=for-the-badge" alt="快速开始" /></a>
  <a href="profiles/message.compose.tool.json"><img src="https://img.shields.io/badge/JCL_Profile-0.1-2F8F68?style=for-the-badge" alt="JCL Profile 0.1" /></a>
  <a href="docs/07-universal-game-spike-zh.md"><img src="https://img.shields.io/badge/Nine_Lights-一致性尖峰-6E5AA8?style=for-the-badge" alt="Nine Lights 一致性尖峰" /></a>
  <a href="docs/i18n/README.md"><img src="https://img.shields.io/badge/UI_语言包-23-D9A441?style=for-the-badge" alt="23 个种子 UI 语言包" /></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/欢迎-共同建设-3978C6?style=for-the-badge" alt="欢迎共同建设" /></a>
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.zh-TW.md">繁體中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a>
</p>

> [!IMPORTANT]
> Jidan 仍是实验原型，不是完整 Android 发行版、提权工具或可托管重要事务的生产助手。请只连接受控 App、测试设备和可丢弃数据。

## ✨ 为什么做 Jidan

今天的软件仍以 App 围墙为中心：一个简单目标要穿过页面、广告、权限和互不兼容的平台接口。Jidan 尝试把软件的最小单位变成一份**能力契约**——AI 可以提出调用建议，但只有确定性的 Host 才能授权和执行。

```text
人的目标 → 语义动作 → 能力契约 → 策略门
         → 已选择的适配器 → 可验证交接回执 → 人类提交
                                              （当前不验证最终发送）
```

长期目标不是再造一个“超级 App”，而是形成一层薄而开放的兼容腰部，让 Android、Apple、Web、HarmonyOS、Windows 以及未来平台实现同一套稳定意图语义。

> **统一语义，不统一实现。** 自然语言与 UI 输入位于 JCL 机器契约之外；Kotlin、Swift、JavaScript、C/C++ 只是 Host 或 Adapter 的实现选择；Web Binding 仍受浏览器沙箱限制。拼音 0.1 已冻结，不是项目底层。参见[历史镜鉴与路线护栏](docs/06-history-lessons-and-route-guardrails-zh.md)。

## 🔌 一份契约，多端实现

[`message.compose`](profiles/message.compose.tool.json) 是第一份 Jidan Capability Layer（JCL）Profile。JCL 0.1 的首个公开序列化采用与 MCP 兼容的 Tool Profile；JCL 本身不是新编程语言，也不绑定某一种传输或会话模型。

```python
from jidan.models import Step, TaskPlan

# 上层只提出能力，不选择平台，也不直接调用 Adapter。
plan = TaskPlan(
    id="compose-demo",
    goal="准备一份消息草稿",
    steps=(Step(
        id="compose",
        capability="message.compose",
        arguments={"content": "下午三点见。"},
    ),),
)
# 可信 Host 继续完成校验、授权、确认、Binding 选择、执行和回执。
# 完整流程见 prototype/message_compose_demo.py。
```

| 稳定契约 | 可替换 Binding | 当前证据 |
|---|---|---|
| `message.compose` | Android Intent | 数据计划；已有经验证的微信原生交接 |
| `message.compose` | Apple Shortcut / Share Sheet | 数据计划 |
| `message.compose` | Web 可编辑草稿 | 数据计划 |
| `message.compose` | 社区 Adapter | 本地注册，不需要中央发布白名单 |

所有结果都必须如实表达现实状态：

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

`handoff_planned` 绝不能冒充“界面已经拉起”。只有真实验证过 Android Picker 才能报告 `handoff_opened`；即便如此，发送仍是 `false`，因为 Jidan 不选择联系人，也不点击发送。

### Nine Lights：一个小型互操作检查

<p align="center">
  <img src="docs/assets/ninelights-icon.png" alt="九灯：三乘三翻灯小游戏图标" width="180" />
</p>

[`game.ninelights.start`](profiles/game.ninelights.start.tool.json) 与
[`game.ninelights.press`](profiles/game.ninelights.press.tool.json) 描述一款确定性的 3 × 3 翻灯游戏。Python CLI 的每个动作都经过 TaskPlan、最小 READ Grant、`JidanRuntime` 和哈希链 Receipt；独立 JavaScript Web Host 则实现相同 Profile，并重放同一份[一致性向量](profiles/conformance/game.ninelights.vectors.json)。

克隆仓库后，可以直接用浏览器打开无依赖的 [Nine Lights Web UI](prototype/web/ninelights.html)，无需构建步骤。

Windows 用户也可以直接启动中文窗口，或打包成带独立图标的单文件 EXE：

```powershell
cd prototype
python -m pip install PyInstaller==6.21.0
python ninelights_gui.py
powershell -NoProfile -File tools/build_ninelights_exe.ps1 -Python python
```

生成文件位于 `prototype/build/pyinstaller/dist/JidanNineLights.exe`。本地开发构建未签名；不要绕过 Windows SmartScreen。只运行由可信检出自行构建的 EXE，并把文件 SHA-256 与构建脚本打印的值比对。若本机策略阻止脚本，请先检查脚本，并采用组织批准的执行方式。

这证明的是外部可观察语义可以共享，不是共享 Runtime、通用游戏语言或 Android/iOS 已适配。边界与运行方法见[小游戏尖峰说明](docs/07-universal-game-spike-zh.md)。

> [!NOTE]
> Pinyin Frontend 0.1 实验已于 2026-08-02 冻结。代码、Profile、演示与测试暂时保留用于兼容和复现，但不再属于活跃路线或快速开始；不接受新语法与新别名。

## 🧭 架构

```mermaid
flowchart LR
    H["人的目标"] --> P["不可信提案来源<br/>AI 规划器 · UI 输入"]
    P --> C["稳定能力<br/>message.compose"]
    C --> G{"确定性安全门<br/>schema · scope · grant · 确认"}
    G --> R["Host 选择 Binding"]
    R --> A["Android"]
    R --> I["Apple"]
    R --> W["Web"]
    R --> N["新平台"]
    A --> M["移动端原生审阅界面"]
    I --> M
    W --> E["Web 可编辑审阅界面"]
    N --> S["Binding 自有审阅界面"]
    M --> Q["可验证交接回执<br/>sent = false"]
    E --> Q
    S --> Q
    M --> X["人类完成最后动作<br/>当前不验证最终发送"]
    E --> X
    S --> X
    G --> L["授权账本"]

    classDef core fill:#195A41,color:#F2F8F5,stroke:#2F8F68,stroke-width:2px;
    classDef human fill:#F5E7BF,color:#3B2A00,stroke:#D9A441;
    class C,G,R,Q core;
    class H,X human;
```

## ✅ 今天已经能做什么

| 层级 | 状态 | 证据 |
|---|---:|---|
| 能力注册与 Schema 校验 | ✅ | 无第三方依赖的 Python 原型 |
| 任务图、限权 Grant、确认门 | ✅ | 确定性预检与执行 |
| 持久重放拦截 | ✅ | SQLite 授权账本 |
| 哈希链执行回执 | ✅ | Runtime Receipt Log |
| 能力定义指纹授权 | ✅ | Grant 绑定 Schema、风险与 Adapter；定义变化即失效 |
| 发现错误分层 | ✅ | 已落地纯分类器与单测；真实连接和回退集成仍待实现 |
| Android 17 AppFunctions | ✅ | 受控 Provider 与真机 Harness |
| 语义表面发现 | ✅ | AppFunctions → RemoteInput → Shortcut → 公开分享 |
| 微信原生交接验证 | ✅ | 验证准确 Picker；不选人、不发送 |
| 跨端 `message.compose` Profile | 🧪 | Android / iOS / Web 计划；Android 已验证 Binding |
| Nine Lights 语义尖峰 | 🧪 | Python Runtime/Receipt + 独立 JS Host；共享向量 |
| Pinyin Frontend 0.1 | ⏸️ | 冻结兼容实验；不新增语法或别名 |
| 生产级移动 Agent OS | 🗺️ | 尚未宣称完成 |

## 🛡️ 把安全写进结构

- **AI 规划器不是安全边界：**模型输出始终按不可信数据验证。
- **开放发布不等于盲目执行：**任何人都能实现 Adapter，但本机仍掌握安装信任、策略、隔离与撤销。
- **收件人提示不是授权：**`message.compose.recipient` 永远不会传给平台 Binding。
- **输入 Frontend 不是授权：**语言或 UI 输入不能发 Grant、执行、选择平台或改写已经确认的正文。
- **Adapter 无权宣布成功：**发送状态由 Host 生成，不照抄第三方返回值。
- **授权不只绑定名字：**Grant 绑定能力定义指纹；同名能力的 Schema、风险或 Adapter 变化后必须重新授权。
- **模糊结果不会被重试成成功：**未知就是未知，并保守写入回执。
- **用户拥有最后一步：**发送、支付、删除和安全设置必须具有明确提交边界。

连接真实设备前请阅读 [SECURITY.md](SECURITY.md)。

## 🚀 快速开始

使用 Python 3.11+ 运行完整的无依赖原型测试与跨端演示：

```bash
cd prototype
python -m unittest discover -s tests -p "test_*.py"
python message_compose_demo.py
python ninelights_gui.py --self-test
python ninelights_demo.py --level cross --moves 5
node tools/check_ninelights_web.js
python appfunctions_smoke.py
```

消息演示默认停在 `awaiting_confirmation`；`--simulate-approval` 会明确标成模拟批准，不能当作用户真的确认过。Nine Lights 是本地 READ/COMPUTE 演示，无需人工确认，但 Python 路径仍经过完整 Runtime 与 Receipt 链。

检查全部 Android 语言包：

```bash
python prototype/tools/check_locales.py
```

使用 JDK 17+ 和 Android SDK 37 构建受控 Reference App：

```bash
cd reference-app
./gradlew :app:assembleDebug
```

Windows 请用 `gradlew.bat`。PowerShell 5.1 的 Unicode 注意事项见[原型说明](prototype/README.md#windows-unicode-arguments)。

## 🗂️ 仓库地图

```text
profiles/       与 MCP 兼容的 JCL 能力及一致性向量
prototype/      能力内核、Adapter、策略、授权、回执与演示
reference-app/  受控 Android 17 AppFunctions Provider
docs/           架构、调研、路线图与国际化说明
```

APK、模拟器镜像、原始设备日志、截图、回执和 SQLite 账本不会提交到 Git。

## 🌍 多语言，但不分裂协议

- 任意 Unicode 正文可以穿过 JSON、任务图、ADB、存储、回读和 UI。
- Android Reference UI 已提供 **23 个种子 Locale**，包括 RTL 阿拉伯语。
- `memo: <正文>` 是语言无关的确定性入口。
- 已冻结的 `zh-Latn-pinyin` 实验只为兼容和复现保留。
- 能力 ID、Schema 字段、Grant、哈希和回执值始终保持稳定 ASCII。
- 新增 UI 翻译和受审查的语言 Adapter，不需要 Fork 协议。

种子翻译只是开源起点，不冒充母语人工审校。欢迎在[语言与国际化指南](docs/i18n/README.md)里认领一种语言。

## 🤝 一起建设

我们尤其欢迎：新平台 `message.compose` Binding、能抓住“假成功”的一致性测试、23 个 Locale 的母语审校、不导入 Python Runtime 但能通过共享向量的独立 Nine Lights Host、受约束的语言 Adapter，以及基于受控设备的可复现实验。

从 [CONTRIBUTING.md](CONTRIBUTING.md)、[90 天路线图](docs/04-90-day-execution-roadmap-zh.md)和[近七日协议复盘](docs/08-seven-day-protocol-review-zh.md)开始。

## 许可证

Apache License 2.0，详见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
