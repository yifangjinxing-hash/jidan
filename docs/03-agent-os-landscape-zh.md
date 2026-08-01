# AI-native OS / Agent 前沿竞争雷达

> 截至 2026-08-01。`事实` 来自官方资料或论文；`判断` 是据此做出的产品/架构推断；社区演示不当作量产结论。

## 一张表看清战场

| 阵营 | 已有能力（事实） | Jidan 应学什么 / 避开什么（判断） |
|---|---|---|
| Google / Android | Android 17 AppFunctions、AICore、ADK、AppSearch、Computer Control、Gemini 跨 App 任务 | 最大直接竞争者；方向已验证，但特权准入和模型选择由平台掌控 |
| Apple | App Intents、Foundation Models、Core Spotlight、Private Cloud Compute | 类型化 Action、本地模型和端云隐私体验是标杆；封闭生态留下开放/BYOM 机会 |
| Microsoft | Windows MCP、On-device Registry、App Actions、Agent Workspace | 最值得借鉴的是独立 Agent 身份、隔离桌面、签名注册表和用户接管 |
| HarmonyOS | Intents Kit、Agent Framework Kit、鸿蒙意图框架 | 中国市场最直接竞争；Jidan 不能只研究 Google/Apple |
| OpenAI | ChatGPT agent、Computer Use、MCP/Apps、云端虚拟计算机 | 可作为模型/远程执行供应商；不掌控移动 OS 是合作窗口 |
| 开源研究 | AIOS、AutoDroid、UI-TARS、Mobile-Agent、UFO | 调度、记忆、GUI 数据有用；多数是现有 OS 上的研究 runtime，不是完整手机系统 |
| 开放协议 | MCP 2026-07-28、A2A 1.0 | 直接兼容，别另造传输协议；系统授权、数据流与事务仍需 Jidan 自己解决 |

来源：[Android 17](https://developer.android.com/blog/posts/android-17-is-here)、[Apple Foundation Models](https://developer.apple.com/documentation/FoundationModels)、[Apple App Intents](https://developer.apple.com/documentation/appintents)、[Windows MCP](https://learn.microsoft.com/en-us/windows/ai/mcp/overview)、[Windows Agent Workspace](https://blogs.windows.com/windowsexperience/2025/10/16/securing-ai-agents-on-windows/)、[HarmonyOS Intents Kit](https://developer.huawei.com/consumer/cn/sdk/intents-kit)、[MCP 规范](https://modelcontextprotocol.io/specification/2026-07-28)、[A2A 规范](https://a2a-protocol.org/latest/specification/)。

## 关键趋势

### 1. App 正在从“页面包”变为“能力与实体提供者”

Android AppFunctions 和 Apple App Intents 都让 App 把动作、数据实体和类型信息交给系统智能层。Google 甚至明确把 AppFunctions 称为端侧 MCP。竞争焦点将从“谁拥有最多页面”转为“谁能被系统可靠发现、组合和验证”。

Jidan 的机会不是发明 `function calling`，而是提供跨平台、更开放的控制面：同一个任务图可映射 Android AppFunctions、Apple App Intents、Harmony Intent、MCP、A2A、公共 Intent 和 GUI fallback。

### 2. GUI Agent 从纯视觉循环转向“编译后确定性执行”

早期 AutoDroid/DroidBot-GPT 证明了 UI tree/截图→动作的可行性，但可靠性弱。更新工作如 AutoDroid-V2、ActionEngine 更接近正确方向：模型先生成程序或状态机，随后由确定性执行器回放，只在状态偏离时视觉重定位。[AutoDroid-V2](https://arxiv.org/abs/2412.18116)、[ActionEngine](https://arxiv.org/abs/2602.20502)。

Jidan 应固定使用：

```text
类型化 Action
  → 已编译并验证的 Skill/状态机
  → UI tree 兼容执行
  → 隔离窗口中的截图 VLM
  → 用户澄清或接管
```

每一级都有步数、时间、能耗、网络、金额和数据外发预算；后置条件失败就升级，不允许模型无限猜。

### 3. 端侧小模型已实用，但“参数量=固定延迟”是伪命题

公开可复核结果表明 1B–3B 量化模型已能在旗舰手机上实用，但同一模型会因 SoC、运行时、量化、prompt 长度、冷/热启动和温控产生巨大差异。Meta 的 OnePlus 12/ExecuTorch CPU 测试报告 1B 模型约 50.2 tok/s、TTFT 0.3 秒，3B 约 19.7 tok/s、TTFT 0.7 秒，但只使用 64-token prompt，不能外推到完整任务规划。[Llama 3.2 model card](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/MODEL_CARD.md)。

2026 年跨运行时研究还发现，NPU 上不同框架可能相差最高 10 倍；NPU 常适合 compute-bound prefill，CPU 有时更适合 memory-bound decode。[移动 NPU 推理研究](https://arxiv.org/abs/2607.05475)。

因此 Jidan 的 benchmark 必须拆分冷启动、TTFT、prefill、decode、峰值 RSS、能耗、热降频、计划正确率和副作用率；不能只报 tok/s。

### 4. “记忆”正在变成新的系统数据层

系统级 Agent 需要跨 App 的个人上下文，但无来源的长期向量库会变成不可解释的“向量汤”。Jidan 的 Context Vault 应让每条记忆携带来源、时间、用途、置信度、ACL、TTL 和推导链；用户能查看、修改、导出和彻底删除。AppSearch 可作为 Android 本地结构化索引底座之一，但 Jidan 不能把索引所有权交给单一模型。[AppSearch](https://developer.android.com/develop/ui/views/search/appsearch)。

### 5. Prompt injection 仍是系统级未解问题

MCP 最新规范明确：协议层本身不能替实现者强制执行用户同意、访问控制和工具安全。网页、邮件、文档、屏幕、KDoc 和第三方 MCP 输出都可能是污染源。[MCP 安全原则](https://modelcontextprotocol.io/specification/2026-07-28)。

Jidan 必须在模型之外实施信息流标签、用途绑定和 capability attenuation：不可信内容可以影响“建议做什么”，不能影响“允许做什么”。

## 独立硬件的教训

- Rabbit r1/rabbitOS 基于 AOSP，仍在持续更新；把它简单写成“项目已死”并不准确。[Rabbit r1](https://www.rabbit.tech/newsroom/introducing-r1)、[Rabbit AOSP 说明](https://www.rabbit.tech/blog/making-r1-more-accessible-to-developer-community)。问题信号是：单独硬件缺少默认生态和稳定 Action 协议时，很容易沦为云端代操作入口。
- Humane Ai Pin 的消费者云服务已于 2025-02-28 停止，设备的通话、消息、AI 查询和云功能随之失效；HP 收购其团队、平台与专利。[Humane 停服通知](https://support.humane.com/hc/en-us/articles/34374173951373-Important-Update-for-Consumer-Ai-Pin-Customers)、[HP 收购公告](https://www.hp.com/us-en/newsroom/press-releases/2025/hp-accelerates-ai-software-investments-to-transform-the-future-of-work.html)。

教训：不要同时挑战新硬件、用户习惯、运营商、App 生态和云成本；离线后系统仍必须保有核心价值。Jidan 先做 AOSP/Cuttlefish/GSI、保留 APK 兼容是更稳的楔子。

## 三个最容易被复制或封堵的点

1. **Action 注册表。** Google/Apple 已有同类能力，也能卡默认入口、私有权限和商店政策。防线不是 API 名字，而是开放跨 OS 规范、适配器、合规测试、兼容数据和开发者收益。
2. **聊天入口、Goal Canvas、主动记忆。** 平台方拥有默认分发和账号同步，复制 UI 很容易。防线是用户主权：可导出记忆、BYOM、透明权限账本、可迁移身份与跨设备独立性。
3. **控制旧 App 的 GUI 自动化。** 平台随时可收紧 Accessibility/后台/反自动化。防线是让 GUI 占比持续下降，把主路径转为 Action SDK、AppFunctions、Intent、MCP 和编译 Skill，同时保有可刷写 AOSP/GSI 与 OEM 路线。

## 可防御的核心

Jidan 最值得拥有的不是模型，也不是聊天 UI，而是：

- 真实设备上的能力兼容图；
- 任务级最小授权与数据用途控制；
- 可恢复、可补偿、可验证的跨 App 任务执行数据；
- 用户拥有、带来源的个人上下文图；
- 模型/OS/厂商无关的 JGraph/JCC 开放规范；
- 原生能力与 GUI 漂移的长期评测/回归语料。

这些才是平台方难以用一次系统更新抹平的积累。
