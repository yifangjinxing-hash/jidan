# Android「手 + 脑」实验：Jidan 现在走到哪一步

更新日期：2026-08-12

## 先用一句小孩也能听懂的话说

按键精灵这一类工具像一只很有力的机械手：会看屏幕、找按钮、点按、滑动、输入文字，但它通常只会照剧本干活。

Jidan 想补上的不是另一只手，而是四样东西：

| 东西 | 像什么 | 负责什么 |
|---|---|---|
| Android 无障碍执行器 | 眼睛和手指 | 读出页面里的按钮、输入框，并执行一步动作 |
| Jidan Planner | 脑子 | 把“我要做什么”拆成有顺序的短步骤 |
| JCL 契约 | 写清楚的任务卡 | 规定目标、动作上限、敏感信息怎么传、什么算完成 |
| Receipt 回执 | 行车记录仪 | 记下每一步前后看到了什么、系统是否接收、结果是否真的核验 |

所以当前不是“把 Android 装进 Jidan”，也不是完整独立操作系统。它是一个已经拥有第一只可审计小手的实验性执行内核。

## 目前：第 2 阶段已完成，并落地了一条自有 App 的真实写入切片

1. **能听懂并写任务卡：已完成。** 已有 JCL Profile、策略门、限权 Grant 和哈希回执。
2. **能在自己的实验桌上动手：本次完成。** 真 Android 无障碍服务读页面、填字段、点按钮，并逐步核验。
3. **能看懂真实 App，但先不乱点：契约完成，Android 执行器待接。** `SHADOW` 只生成计划并交给人，不冒充执行成功。
4. **能通过受审计的 Adapter 处理真实小事：已完成一条自有无网清单切片。** 通用 App 与第三方 App 仍需要分别建立身份、版本、页面和结果证据。
5. **成为可替代桌面的 Jidan OS：未完成。** 这还需要 AOSP、系统服务、驱动、设备适配和长期安全维护。

最重要的变化是：项目从“打开支付宝/打开设置的前门演示”，迈到了真正的 **观察 → 计划 → 一步执行 → 重新观察 → 核验 → 写回执**。

## 对提供的按键精灵 APK 做了什么

本节最初只做了离线静态审计；后续又在隔离模拟器上完成了可见启动、QuickDev 浮窗和目标页面走查，但步骤栏仍为空，没有得到可回放脚本。整个过程没有修改或重签它，也没有接触任何真实账户。动态细节见[0.3 历史证据与 0.5 路线](11-daily-note-cross-app-hand-zh.md)。

审计对象是 `com.cyjh.mobileanjian.apk`：

- 包名 `com.cyjh.mobileanjian`，版本 `4.2.3`；
- 文件大小 83,933,160 字节；
- SHA-256：`2D554D35D3C20DE38C2ADB6B51BDEA2DDCF19E4DCDC6F3C3DA52244037BB803D`；
- 它确实包含无障碍节点操作、坐标手势、文字输入、截图、OCR、脚本引擎和多种 native 注入载荷；
- 它声明了 56 个权限，并包含大量广告、统计、远程调试、Socket 和动态执行组件；
- 没有发现适合 Jidan 正式依赖的公开、稳定、带身份校验的 SDK、AIDL 或第一方 deeplink。

完整的机器可读结论见 [`com.cyjh.mobileanjian-4.2.3.audit.json`](audits/com.cyjh.mobileanjian-4.2.3.audit.json)。

结论不是“这个 APK 没用”，而是：**它证明了手可以很强，但不适合作为 Jidan 的骨头。** 直接把脑子接进一个权限巨大、接口私有、供应链很宽的黑箱，会让 Jidan 的开放性、可替换性和可核验性一起消失。我们取它最有价值的形状——节点、手势、输入、截图、OCR——重新造一只很小、能看清每根手指的手。

## 社区最近反复踩中的坑

本节只采用论坛、GitHub issue、Reddit 和独立开发者讨论，不采用官方信源。

- **节点树不是真相，“手”必须可换。** 2026-08-11 的 [agent-device #1733](https://github.com/callstack/agent-device/issues/1733) 报告透明覆盖层让几十个 Telegram 节点被解析成一个；修复节点后，输入框能聚焦却仍写不进文字。2026-08-05 至 09 的 [mobile-mcp #399](https://github.com/mobile-next/mobile-mcp/issues/399)、[#402](https://github.com/mobile-next/mobile-mcp/pull/402) 和 [#403](https://github.com/mobile-next/mobile-mcp/pull/403) 又暴露递归节点丢失和小数中心坐标不被执行器接受。JCL 应保存原始观察证据并描述语义目标，把树解析、OCR、视觉和最终整数坐标都留在可替换的 Hand Adapter 里；不能让某个自动化后端变成协议本身。
- **“开关亮着”不等于服务活着。** 2026-08-11 的 [GKD #1430](https://github.com/gkd-kit/gkd/issues/1430) 追到已启用服务值被其他组件覆盖；2026-08-06 的 [Android Remote Control MCP #142](https://github.com/danielealbano/android-remote-control-mcp/issues/142) 则因组件短名、长名不一致，把可用服务误判为禁用。Jidan 每次动作会话都需要真实状态探针：服务连接、目标包/窗口、首帧节点和超时缺一不可，不能只读一个设置字符串。
- **后端回执不等于页面成功。** 2026-08-10 的 [agent-device #1721](https://github.com/callstack/agent-device/issues/1721) 中，缺失字段的输入落进上一个仍聚焦的控件，工具却返回完成；2026-08-11 的 [xiaohei-phone-agent #103](https://github.com/toolazytoname/xiaohei-phone-agent/pull/103) 也专门补上了同应用重新观察。Jidan 必须把 `attempted / os_accepted / observed / transition_verified / outcome_unknown` 分开，并把包名、窗口、节点和观察快照绑定；一步一重看、一后置条件，无法核验就停且不自动重试。
- **一台设备同一时刻只能有一只手。** 2026-08-11 的 [agent-device #1729](https://github.com/callstack/agent-device/issues/1729) 直接暴露两个 Agent 同时控制一台手机的冲突，后续修复引入了独占控制。Reddit 楼中楼也有人要求 [按工具授权、可见作用域和审计](https://www.reddit.com/r/MachineLearning/comments/1rf1u76/comment/o7wmjkt/)，并指出用户触摸与 Agent 动作会互相踩踏。Runtime 因而需要带超时的单设备独占租约、明确的人工接管和全局停止；租约丢失后不得续点。
- **控制状态应可见，但秘密不能上屏。** 2026-08-09 的 [Android Remote Control MCP #143](https://github.com/danielealbano/android-remote-control-mcp/pull/143) 为远控增加轻量可见层；另一条 Reddit 楼中楼回复直言，即使作者强调隐私，用户仍[不愿在主力手机安装](https://www.reddit.com/r/androiddev/comments/1vbpxwd/comment/p0v7ue0/)。Jidan 应让人随时看见“谁在控制、能否停止、现在是否交还人手”，但浮层和日志不得显示页面正文、参数、密码或验证码；实验也应先从测试设备开始。
- **设备行为必须能记录、回放和复现。** 2026-08-07 的 [agent-device #1680](https://github.com/callstack/agent-device/issues/1680) 把录制/回放需求指向同一个根因：设备、系统和节点树会漂移。模拟器的观察快照、动作、时间预算与结果应成为可脱敏回放的测试轨迹，用来做故障注入和回归，而不是只留一张成功截图。
- **先路由，再动作；模型只处理分支和例外。** V2EX 的讨论分别指出[整树上下文会过期](https://v2ex.com/t/1182284)、[应先选路线再执行](https://v2ex.com/t/1195562)、[AutoJS 在企业微信/QQ 中会误操作](https://www.v2ex.com/t/1203836)、[纯坐标容易漂移](https://v2ex.com/t/1178238)，以及一次任务[可能慢到接近一分钟](https://v2ex.com/t/1178943)。Reddit 楼中楼给出的实用模式也是[先让强模型探索，再固化成脚本](https://www.reddit.com/r/androiddev/comments/1vbpxwd/comment/p0varfz/)。因此高频已知路径优先走可测试 Adapter；模型只做意图路由、歧义提问和失败恢复，不逐帧自由发挥。
- **页面文字是不可信数据，不是新指令。** [Playwright MCP #1479](https://github.com/microsoft/playwright-mcp/issues/1479) 展示网页内容可以伪装成给 Agent 的指令；Android 的无障碍节点、OCR 和通知正文同样可能携带提示注入。观察层必须把屏幕文字标成外部数据，它不能改写用户目标、扩大权限、取消接管点或自己发起新动作。
- **看不见必须成为合法结果。** [GKD #1243](https://github.com/gkd-kit/gkd/issues/1243)、[#1420](https://github.com/gkd-kit/gkd/issues/1420)、[Maestro #1126](https://github.com/mobile-dev-inc/maestro/issues/1126) 和 [uiautomator2 Flutter #1191](https://github.com/openatx/uiautomator2/issues/1191) 都说明 WebView、Flutter、Canvas 不能假设有标准节点树。`NO_SEMANTICS` 应明确交还人手，或切到有来源标记的 OCR/视觉 Adapter，不能偷偷用旧坐标猜。
- **感知也必须有预算。** [uiautomator2 #1173](https://github.com/openatx/uiautomator2/issues/1173) 报告频繁拉整棵 DOM 造成内存问题，[#1174](https://github.com/openatx/uiautomator2/issues/1174) 则显示底层超时可能远超声明值。Host 必须自己限制观察次数、节点量、总时长和重试次数；厂商冻结、真实金融 App 拒绝无障碍等情况则直接交还人手，而不是绕过系统限制。

这些讨论把 Jidan 的 Android 路线压成五条硬规则：**手可替换、状态靠探针、单设备独占租约、动作后重新观察核验、屏幕内容一律按不可信输入处理。** 社区真正反感的不是“AI 操作手机”，而是一只不知道自己点没点对、失败后还继续乱点、同时又能读取整屏秘密的无限机械手。

## 这次实际造出的东西

### 1. 三个职责分开的 Android APK

- **Jidan Shell**：脑子、策略、无障碍服务和回执都在这里。
- **小事清单**：自有、无网络、可撤销的真实本机写入目标。
- **鸡蛋操作实验室**：自有的假支付页面；没有 `INTERNET` 权限，不连接真实账户，不生成订单，不移动资金。

Shell 启动实验前会同时核对：固定包名、签名身份、固定版本、实验契约、`debuggable` 实验标志和没有网络权限。任何一项不对都会直接阻断；`SHADOW` 目前只是尚未接入 Android 观察器的规格契约，不是可偷偷兜底的执行通道。

无障碍服务当前只订阅两个固定的自有包：隔离实验室和小事清单，不常驻收集其他 App 的页面。执行器也没有开启坐标手势，只认稳定的语义节点 ID。小事清单的后续动态走查和真实持久化证据见[0.3 历史证据与 0.5 路线](11-daily-note-cross-app-hand-zh.md)。通用第三方 App 执行和按键精灵命令入口仍未接通。

### 2. 一条真的跑过的敏感动作链

2026-08-12 的 0.3 历史构建在已启用“鸡蛋辅助操作”的 Android 17 模拟器中，用户只点了一次“手 + 脑实验”，随后 Jidan 完成并核验了：

1. 填写虚构收款人；
2. 填写虚构金额；
3. 填写假支付密码；
4. 填写假验证码；
5. 点击“提交假实验”。

最终页面显示“实验完成：外部交易 0 笔”。业务语义上共有 5 个动作结果；硬化后的回执为每个动作先同步写入 `PREPARED`，再写入 `RESULT`，因此一轮完整成功执行会留下 10 条链式记录。5 条 `RESULT` 应全部为 `transition_verified`，最后一个动作标记 `syntheticCommit=true`、`realPayment=false`。密码和验证码只以当前会话里的短命引用传递，提交后立即清空；它们的原文不会写进 Jidan 计划、回执或实验应用存储。

![Android 手脑实验完成画面](assets/jidan-hand-brain-lab-0.2.png)

### 3. 一个启动入口与两条互不混淆的 JCL 通道

- [`android.ui.sandbox_start`](../profiles/experimental/android.ui.sandbox_start.tool.json)：Shell 本地注册的空输入启动入口；用户明确点一次后，Host 才观察实验页并在内部生成计划。
- [`android.ui.sandbox_execute`](../profiles/experimental/android.ui.sandbox_execute.tool.json)：只准描述自有无网络实验包中的 PAYMENT、PASSWORD、OTP 合成流程；它目前是未注册的 Adapter 契约，Android Runtime 使用内部 Kotlin 映射，不接受外部 JSON 计划。
- [`android.ui.shadow_plan`](../profiles/experimental/android.ui.shadow_plan.tool.json)：规格上可以描述真实 App 的敏感步骤，并把 `executorAttempted` 固定为 `false`；Android 真实 App 观察器尚未接入。

共享的 [`jcl.ui-action-plan-v0.1`](../profiles/schemas/jcl.ui-action-plan-v0.1.schema.json) 要求页面指纹、前置/后置条件、执行预算、恢复点、效果状态和现实状态。公共契约不接受屏幕坐标，也不接受密码、OTP 明文，只接受短命的 opaque reference。它采用 MCP 兼容的 Tool 数据形状，但仓库目前没有对外注册 Android MCP Server 或 JSON 执行端点。

### 4. 一个不能自封可信的“手”目录

[`JCL-Hand-Provider/0.1`](../profiles/schemas/jcl.hand-provider-v0.1.schema.json) 把执行后端单独登记。计划同时绑定 `handProviderId` 和 Provider 清单摘要；清单、计划 Schema 或本机 Adapter 任一变化，都不能静默沿用旧绑定。Python 中的传输无关 MCP Gateway 只公布 Host 已注册的 Tool，并在调用执行器之前和之后分别校验输入、输出 Schema。

- 合成实验手是 `OWNED_RUNTIME_LOCAL_VERIFIED / SANDBOX`，小事清单手是 `OWNED_RUNTIME_LOCAL_VERIFIED / OWNED_APP`；二者都只在本机内部 Kotlin 映射中运行；
- 按键精灵是 `CANDIDATE_UNBOUND / HANDOFF_ONLY`，Shell 可以在精确版本与签名匹配时打开它的首页，但它不能绑定 executor，也不能借 MCP 参数给自己提权；
- `android.ui.sandbox_execute` 仍明确写着 `registered=false`。这意味着插座和防呆卡口已经做出来，外部 MCP 客户端直通 Android 的桥还没有冒充完成。

这不是永久禁止支付、密码或验证码。相反，敏感能力现在有了可以真正生长、注入故障和反复测试的实验桌；只是不能用假实验的成功去冒充真实付款成功。

## 普通人怎么试玩

需要 Android 8.0 或更高版本。先安装小事清单与实验室，再安装 Shell：

```powershell
adb install -r -t reference-app/daily-demo/build/outputs/apk/debug/daily-demo-debug.apk
adb install -r -t reference-app/accessibility-sandbox/build/outputs/apk/debug/accessibility-sandbox-debug.apk
adb install -r -t reference-app/shell/build/outputs/apk/debug/shell-debug.apk
```

第一次只按这个顺序做；“手 + 脑实验”只点一次，不需要返回后再点第二次：

1. 打开 **Jidan Shell**，点一次 **手 + 脑实验**；
2. 如果 Android 跳到无障碍设置，请亲自打开 **鸡蛋辅助操作**；
3. 返回 Shell；服务就绪后会自动继续。

如果系统此前已经授权，第 2 步会被跳过，实验会在第一次点击后直接开始。

看到“实验完成：外部交易 0 笔”只表示页面到达了合成终态；完整链路还要以 5 个动作各自成对的 `PREPARED / RESULT` 回执和后置条件核验为准。

## 下一步该做什么

下一阶段不应该马上追求“全手机随便点”，而应完成三个很窄但关键的东西：

1. 把 Android 的 `SHADOW` 观察器接上一个用户明确选择的真实 App，只展示它看见了什么、准备做什么，执行次数保持 0；
2. 为节点树缺失的 WebView/Flutter 页面做独立视觉 Adapter，并把 `A11Y / OCR / VISION` 来源写进证据；
3. 在已经落地的小事清单之外，再选第二个无钱、可撤销的日常微动作，从影子计划逐步升级为真实执行 Adapter，再用结果回执证明它不是“点过就算成功”。

先让这只手做到 **少、准、能停、能解释**，然后再逐渐扩大它能碰的世界。
