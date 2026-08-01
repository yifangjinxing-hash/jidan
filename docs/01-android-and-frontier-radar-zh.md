# Android 与 Agent OS 前沿雷达

> 信息截点：2026-08-01。优先采用 Android/AOSP、Apple、协议规范和论文等一手资料。

## 1. 先回答“现在安卓最新框架是什么”

“Android 框架”至少有三种含义，不能只报一个版本号：

| 层级 | 当前状态 | 对 jidan 的意义 |
|---|---|---|
| 操作系统平台 | Android 17 / API 37，2026-06-16 稳定发布 | 首个明确自称从 OS 转向 `intelligence system` 的 Android 稳定版 |
| App 开发栈 | Kotlin 2.4.10、Jetpack Compose 1.11.4、Material 3 1.4.0、AGP 9.3.0、JDK 17 | Shell 原型应采用 Kotlin + Compose；Views 保持兼容但不作为新 UI 主线 |
| Agent 栈 | AppFunctions 1.0.0-alpha10、ADK for Android、ML Kit Prompt API、AICore/Gemini Nano、Android Computer Control Preview | Android 已开始把 App 功能转为 Agent 可调用工具，并为未适配 App 增加 GUI 自动化 |

版本依据：[Android 17 发布公告](https://developer.android.com/blog/posts/android-17-is-here)、[Compose 发布页](https://developer.android.com/jetpack/androidx/releases/compose)、[Kotlin 发布记录](https://kotlinlang.org/docs/releases.html)、[AGP 9.3](https://developer.android.com/build/releases/agp-9-3-0-release-notes)、[AppFunctions 发布页](https://developer.android.com/jetpack/androidx/releases/appfunctions)。

## 2. Android 的底层到底是什么

典型调用链如下：

```text
App / Compose / SDK / NDK
        ↓ Binder + AIDL
Android Framework 与 system_server 系统服务
        ↓ Binder + Stable AIDL
ART、原生库、原生守护进程、HAL 服务
        ↓
vendor / odm 厂商实现与驱动模块
        ↓
Android Common Kernel / GKI / Linux 内核
        ↓
CPU、GPU、NPU、显示、相机、音频、基带等硬件
```

- App 通过 Framework API 与系统服务交互；ART 执行 DEX，原生代码经 NDK/JNI 进入原生层。[AOSP 架构总览](https://source.android.com/docs/core/architecture)、[ART](https://source.android.com/docs/core/runtime)。
- Binder 是 Android 进程间通信主干，AIDL 描述接口；新 HAL 应使用 Stable AIDL，HIDL 已弃用。[Binder](https://source.android.com/docs/core/architecture/ipc/binder-overview)、[AIDL HAL](https://source.android.com/docs/core/architecture/aidl/aidl-hals)。
- Treble/VINTF 把 framework 与 vendor/BSP 解耦；GKI/KMI 再把通用内核与厂商模块解耦。这些层是 Android 能覆盖大量硬件的真正壁垒。[分区架构](https://source.android.com/docs/core/architecture/partitions)、[Android common kernel](https://source.android.com/docs/core/architecture/kernel/android-common)。
- App 隔离不只是一项权限：独立 UID、SELinux default-deny、seccomp、Scoped Storage、AppOps、签名/角色/特权权限和后台执行限制共同构成边界。[Application Sandbox](https://source.android.com/docs/security/app-sandbox)、[SELinux](https://source.android.com/docs/security/features/selinux)。

因此，首版替换 Linux、Binder、ART、HAL 或驱动没有产品收益，却会立即继承 BSP、基带、相机、运营商认证、CTS/VTS、OTA 和安全响应的全部成本。jidan 应复用这些层，只重做其上的 Agent 控制平面。

## 3. Android 17 已经走到哪里

### AppFunctions：结构化能力入口

AppFunctions 把 App 的数据和动作注册成可发现、带类型和自然语言描述的端侧工具，Google 称其为 Android 里的 MCP 等价物。平台能力从 Android 16 起存在，Android 17 扩展了能力；Jetpack 库目前仍为 alpha，Gemini 的完整接入仍是 private preview。[官方概览](https://developer.android.com/ai/appfunctions)、[Android 17 的 AppFunctions](https://developer.android.com/blog/posts/android-17-is-here)。

关键限制不是 API 写法，而是分发权限：跨包发现和调用需要 `EXECUTE_APP_FUNCTIONS`，该权限当前只给 privileged system app 或配置中的 known signer，保护级别为 `internal|privileged|knownSigner`。[Manifest 权限定义](https://developer.android.com/reference/android/Manifest.permission#EXECUTE_APP_FUNCTIONS)、[AppFunctionManager](https://developer.android.com/reference/android/app/appfunctions/AppFunctionManager)。

结论：普通商店 APK 可以暴露自己的 AppFunctions，却不能成为任意跨 App 的总调度器。实验室可用官方 Testing Agent + shell identity；产品要走系统镜像、known signer 或 OEM 预装。

### Android Computer Control：GUI 降级入口

Computer Control 让 OEM 预装助手在安全后台虚拟显示中运行目标 App，循环截图、推理并注入 tap/swipe/text；首次使用有系统授权，可把控制权交还用户。当前为 Preview、目标 App 有限、单次最多 6 个 App、系统同时只允许一个会话，并要求 privileged `ACCESS_COMPUTER_CONTROL`。[官方说明](https://developer.android.com/ai/computer-control)。

这验证了 jidan 的“结构化能力优先、GUI 自动化兜底”路线，也证明 Accessibility 不应成为量产架构。它可用于 stock Android 研究原型，但权限过宽、策略风险高、UI 漂移严重。

### 端侧 Agent 与模型

- ADK for Android 已支持 Kotlin/Java Agent，并可通过 ML Kit 在端侧使用 Gemini Nano，也可组合本地子 Agent 和云端根 Agent。[ADK for Android](https://developer.android.com/ai/adk)。
- AICore 统一管理 Gemini Nano、模型更新、安全过滤和硬件加速；自有模型可走 LiteRT。[Gemini Nano/AICore](https://developer.android.com/ai/gemini-nano)、[Android AI 选型](https://developer.android.com/ai/overview)。
- Prompt API 当前输入低于 4,000 token；AICore 有每 App 推理/电池配额，不支持解锁 bootloader 的设备。[Prompt API 限制](https://developers.google.com/ml-kit/genai/prompt/android/get-started)。
- 更致命的是：ML Kit GenAI 推理只允许 App 位于最前台，前台服务也会返回 `BACKGROUND_USE_BLOCKED`；长期使用还可能触发 `PER_APP_BATTERY_USE_QUOTA_EXCEEDED`。[ML Kit GenAI 配额与后台限制](https://developers.google.com/ml-kit/genai)。

因此，不能把 Gemini Nano/AICore 当成 jidan 唯一调度器。正确做法是：规则与小分类器常驻，轻量 SLM 处理歧义和 DAG 生成，重推理按用户策略切云端；自建 LiteRT 路径覆盖纯 AOSP 与解锁开发机。

## 4. 用户补充材料的事实校准

### AIOS

AIOS 是真实且有价值的研究项目，其 kernel 管理 Agent 的 LLM 请求、上下文、内存、存储、工具与访问控制，并报告在其任务设定下最高 2.1 倍吞吐提升。[AIOS 论文](https://arxiv.org/abs/2403.16971)、[AIOS 开源项目](https://github.com/agiresearch/AIOS)。

但它不是可刷入手机、替代 AOSP 的移动 OS；更准确地说，它是运行在现有 OS 之上的 Agent 资源管理层。jidan 可以借鉴调度与上下文隔离，不能把其热度当作手机系统已被验证。

### AutoDroid / DroidBot-GPT / GUI Agent

这条研究线成立：AutoDroid、DroidBot-GPT 等把 UI 状态转成模型可理解表示，再生成操作。[AutoDroid](https://github.com/MobileLLM/AutoDroid)、[DroidBot-GPT](https://arxiv.org/abs/2304.07061)。2026 年的 MobileExplorer 进一步研究端侧 GUI Agent，报告端到端延迟下降 23%。[MobileExplorer](https://arxiv.org/abs/2605.26546)。

但 GUI 自动化还远非“已解决”：2026 年 AndroidDaily 在 94 个真实闭源 App、350 个任务上评测，最强模型成功率仅 62%。[AndroidDaily](https://arxiv.org/abs/2605.27761)。这足够作为覆盖缺口的 fallback，不足以充当系统的稳定 ABI。

### “0.6B–3B 模型几百毫秒完成任务图”

方向合理，但不能作为跨设备事实写入商业承诺。速度受模型、输入长度、prefill/decode、量化、NPU delegate、温度、散热和是否已 warmup 强烈影响；Android NPU 生态也存在厂商碎片。首版应把它定义为待测假设：在 3 档设备上分别测首 token、完整结构化计划、能耗和热降频，不用单一 tok/s 替代任务时延。

## 5. 开放协议正在形成，但安全仍未被协议解决

- MCP 2026-07-28 版把 Host/Client/Server、资源、提示、工具、异步任务、Skills 和 MCP Apps 进一步标准化；规范同时明确，协议本身不能强制用户同意和工具安全，落地者必须实现授权和数据保护。[MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)。
- A2A 1.0 定义 Agent Card、Task、Message、Artifact 和 JSON-RPC/gRPC/HTTP 绑定，适合 Agent 间发现与长任务协作。[A2A 1.0 规范](https://a2a-protocol.org/latest/specification)。

jidan 不应另造网络协议：MCP 用于 Agent→工具，A2A 用于 Agent→Agent；jidan 的原创价值应落在设备级 capability attenuation、数据用途绑定、可撤销授权、用户确认、执行回执和补偿/回滚。

## 6. 真正的机会窗口

Android 已证明方向，但当前实现是平台方拥有、OEM/known signer 优先、Gemini 集成受控。jidan 的可防御差异不是“也有一个聊天助手”，而是：

1. 用户拥有的能力账本，而非厂商拥有的全局助手权限。
2. 模型可替换、本地/云端可路由，不锁定 Gemini 或单一厂商。
3. 每个任务使用衰减后的短期授权，不给 Agent 永久超级权限。
4. 结构化能力、Intent、GUI 自动化使用同一个任务 IR 和回执格式。
5. 开放 SDK 与自助接入，而不是 private preview 白名单。
6. 从 Android Shell 到 AOSP system service 的连续迁移路径。

最重要的判断：Android 的安全边界不是“绊脚石本身”；它们是在阻止 Agent 变成系统级恶意软件。jidan 要颠覆的是授权、组合和交互模型，而不是取消隔离。
