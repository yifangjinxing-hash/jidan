# 2026-07-27—2026-08-02 协议复盘：JCL 应更薄，Host 应更强

> 核验截止：2026-08-02，时区为 Asia/Shanghai。本文把资料分成 **已发布事实**、**尚未合并的提案**、**社区观点**和 **JCL 路线推断**。GitHub 中处于 Open 状态的 PR 均不视为现行 MCP 规范。

## 一页结论

近七天最重要的变化不是“又出现一种 AI 语言”，而是 MCP 正在主动退回一条更薄的协议边界：请求无状态、状态显式传递、扩展可选、平台与 Host 自己承担授权和安全责任。

这使 JCL 的路线更清楚：

1. **JCL Core 只统一动作语义**：Capability ID、输入输出 Schema、风险、确认要求、结果状态和一致性向量。
2. **Host 才是权力边界**：Policy、Grant、确认、幂等、执行回执和本机信任不能交给模型或 Adapter 自报。
3. **MCP、Android AppFunctions、Apple App Intents 是平级 Binding**：都可接入，但任何一家都不能成为 JCL 地基。
4. **不再扩张成 DSL、Agent 编排协议或统一 Runtime**：自然语言是输入，A2A 是另一条 agent-to-agent 边，平台代码保持原生。

## 已发布事实

### 1. MCP 2026-07-28 正式改为无状态核心

**事实。** MCP 于 2026-07-28 发布正式规范，移除了 `initialize` / `initialized` 和 `Mcp-Session-Id`；请求改为自包含，服务端必须实现 `server/discover`，客户端可选择预先发现；Streamable HTTP 请求新增必需的 `Mcp-Method` / `Mcp-Name`；列表结果带缓存提示；MRTR 使用 `input_required` 与 `inputResponses`；Tasks 移到可选扩展；Roots、Sampling、Logging、旧 HTTP+SSE 和 DCR 进入至少十二个月的弃用期。授权侧增加 RFC 9207 issuer 校验和凭据 issuer 绑定。

- [MCP 2026-07-28 发布稿](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [MCP 2026-07-28 权威规范](https://modelcontextprotocol.io/specification/2026-07-28)
- [完整变更表](https://modelcontextprotocol.io/specification/2026-07-28/changelog)

**必须保留的边界。** 去掉协议会话不等于应用没有状态。跨调用状态改为显式、由服务端生成并作为普通参数传递的 handle。规范也明确写道：Tool description 和 annotation 默认不可信；MCP 本身不能在协议层强制同意、授权和访问控制，这些责任落在 Host。

**JCL 推断。** JCL 不应复制 MCP 的传输生命周期、Header 或握手。与 MCP 兼容的 Tool Profile 可以继续保留，但它只是 JCL 的一种公开序列化。

### 2. Android AppFunctions 仍是受限的 Android 专属入口

**事实。** Android 官方页面最后更新于 2026-07-31 UTC，仍将 AppFunctions 标为 experimental preview。它由 Android 平台 API 和 Jetpack 组成，让应用像 on-device MCP server 一样暴露可发现函数；适用于 Android 16+，跨包调用方需要 `EXECUTE_APP_FUNCTIONS`。Gemini 端到端接入仍是 trusted testers 私测，只有有限应用和系统 Agent 可使用完整链路，报名 EAP 也不保证获得访问权。

- [Android AppFunctions 官方概览](https://developer.android.com/ai/appfunctions?hl=en)

**JCL 推断。** AppFunctions 是优先级很高的 Android Binding，但其 Kotlin 注解、XML 索引、系统权限和 OS Registry 不进入 JCL Core。JCL 必须保留 Intent、RemoteInput、Shortcut 或公开分享等降级路径。

### 3. Claude 的新规范支持仍处于逐步上线

**事实。** Anthropic 在同日公告中使用的是 “rolling out across Claude products soon”，而不是“所有 Claude 客户端已经支持”。规范发布、SDK 发布和终端 Host 可用是三件不同的事。

- [MCP 2026-07-28 在 Claude 的支持说明](https://claude.com/blog/bringing-mcp-2026-07-28-to-claude)

**JCL 推断。** 兼容性声明必须绑定具体的 spec、SDK、Host、transport 与测试日期，不能只写“支持 MCP”。

### 4. 开源 MCP App 的执行前确认仍明显不足

**研究事实，但不是正式标准。** 2026-07-29 发布 v2 的预印本分析了 1,723 个 GitHub 开源 MCP App：85.2% 使用文件配置，81.1% 使用官方 SDK；仅 37.2% 实现阻塞式执行确认，62.8% 没有执行前审批，20.0% 连 allowlist 或 approval 这样的主动 Gate 都没有。

- [An Empirical Study of Model Context Protocol Applications](https://arxiv.org/abs/2607.25635)

**限制。** 这是静态 GitHub 开源样本和 LLM 辅助分类形成的时点快照，不能直接外推所有商业产品。作者另行抽样复核并报告 96.5% 的总体分类准确率。

**JCL 推断。** `riskLevel` 或 Tool annotation 不能代替真实确认。WRITE、SEND、DELETE、PAY 和安全设置应在 Host 中形成结构性 Commit Gate。

## 仍是提案，不是规范

| 日期 | 提案或问题 | 已核验内容 | JCL 现在应怎么做 |
|---|---|---|---|
| 2026-08-01 | [Request Idempotency PR #3182](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3182) | 提议给 `tools/call` 增加 `idempotencyKey` 与能力协商；当前仍为 Open | 不等合并，自有 Host 幂等；但不要声称这是 MCP 标准字段 |
| 2026-08-02 | [`oneOf` 类型绕过修复 PR #3185](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3185) | 已用 AJV 复现：把属性类型只放在 `oneOf` 分支，可让错误类型藏在未命中的分支中通过 | 0.x 保持 Schema 小子集；开放组合关键字前先加入恶意负例 |
| 2026-07-27 | [Signed Capability Declarations PR #3140](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3140) | 提议 JWS Manifest、Publisher 身份、内容哈希和变更后重新 Gate；尚无实质性评审 | 可先 pin Profile/Adapter hash 和来源；签名只能证明来源与完整性，不能证明风险标签诚实 |
| 2026-07-29 | [Recovery Metadata PR #3172](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3172) | 提议用 Tool annotation 描述补偿操作；仍为 Open | 不根据不可信 annotation 自动回滚；补偿仍需受信 Profile、Policy 和 Grant |
| 2026-07-27 | [历史 SEP 与当前 Tasks 表面冲突 #3142](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/3142) | 实现者曾被旧 SEP 中已移除的方法误导；维护者说明 [SEP 是历史记录](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/3142#issuecomment-5124136582) | 运行时只认当前规范、Schema 与一致性向量，不把历史提案当契约 |

幂等 PR 的楼中楼指出了一个直接影响 JCL 的缺口：提案只用 Tool Name 和 `arguments` 判断“同一操作”，却漏掉 MRTR 的 `requestState` 与 `inputResponses`；其参考实现还把 Key 放进 Tool 参数、在 Handler 内去重，没有真正演示所提议的协议字段。[完整审查意见](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3182#issuecomment-5151553269)

因此，JCL 的操作摘要应覆盖 Profile/Capability 版本、规范化参数、确认内容以及未来可能出现的 continuation state；相同 Key 配不同摘要必须在 Adapter 前失败。

## 社区楼中楼：真正的争议是什么

社区评论不是事实来源，但能揭示迁移成本和用户预期。以下观点均已回到原帖及回复链核对。

### HN：旧系统能继续跑，不代表新旧可以直接互通

2026-07-28 的 [HN 上指向官方发布稿的讨论帖](https://news.ycombinator.com/item?id=49088058) 有 40 条评论。

- MCP 维护者说，已有代码可以继续运行，只有采用新能力才必须变化。[维护者回复](https://news.ycombinator.com/item?id=49088228)
- 网关/Registry 运营者则指出，新旧 Wire Format 双向不兼容，许多 SSE-only Client/Server 要适配，网关可能成为迁移层。[运营者回复](https://news.ycombinator.com/item?id=49090041)

这两点并不矛盾：旧部署可以原样存活，但跨代互操作需要版本探测、双栈或 Bridge。

同一楼中楼还暴露了两个未解决问题：

- 实作者抱怨文件、图片和 Base64 在不同客户端中处理不一致；MCP Lead Maintainer 回复说文件传输工作本版被延期。[问题](https://news.ycombinator.com/item?id=49089597) / [维护者回复](https://news.ycombinator.com/item?id=49090221)
- 反方认为 Skills + `curl` + 普通 HTTP 已足够，MCP 增加了中间层。[反方观点](https://news.ycombinator.com/item?id=49091546) 楼中楼的回应是：MCP 的增量价值在可发现 Tool、Host 确认、统一 OAuth 和私网隔离，而不只是发送 HTTP。[回应一](https://news.ycombinator.com/item?id=49092293) / [回应二](https://news.ycombinator.com/item?id=49092431) / [回应三](https://news.ycombinator.com/item?id=49092777)

**JCL 路线修正。** JCL 必须能回答“为什么不是 REST/curl”：答案应是跨平台动作语义、确定的风险/确认边界和可验证回执，而不是另一套传输。

### Reddit：远端部署收益明显，本地用户短期感知较小

- [r/ClaudeCode 高互动主帖](https://www.reddit.com/r/ClaudeCode/comments/1v964qc/mcp_just_got_its_biggest_update_since_launch/)
- [r/mcp 规范细读帖](https://www.reddit.com/r/mcp/comments/1v9or4b/the_20260728_model_context_protocol_specification/)

一种观点认为，无状态让远端服务更容易扩容、故障恢复和按请求计费，Tasks 也统一了长任务；另一种观点认为，本地 `stdio` 用户日常几乎不变，CLI 仍会覆盖大量场景，MCP 越来越像 REST/OpenAPI。第二帖还提醒：标题没有突出弃用项，而且“无状态”并不消灭应用状态，显式 handle 仍然必要。

另一个 [7 月 28 日的技术帖](https://www.reddit.com/r/HowToAIAgent/comments/1v980b9/mcp_is_stateless_now_notes_on_what_actually/) 提到每请求 `_meta` 开销、通知为 best effort、仍需 Polling；但其回复基本只有感谢，因此不把它包装成社区共识。

### Apple：有 PoC，不等于开放了公共协议

2026-07-31，一位开发者声称通过 macOS 27 内部 `AgentIntent` / Model Delegation 把 Claude 接入 Siri。[原帖](https://www.reddit.com/r/MacOSBeta/comments/1vbe2ki/apples_rumored_siri_extensions_quietly_shipped_in/)

帖子同时写明：它依赖 Apple 私有 entitlement `com.apple.developer.model-delegation`，开发时需要关闭 SIP/AMFI；作者在回复中也承认这只是 PoC，真正发布仍要 Apple 开放 entitlement。评论主要询问 Gemini 和默认模型，没有形成充分的技术复核。

**JCL 路线修正。** 这不能证明 Apple 已向任意第三方开放 Agent 互操作；Apple App Intents / Model Delegation 仍只能作为受平台规则约束的 Binding，并应保留 Shortcut / Share Sheet 降级。

Apple Developer Forums 在本窗口内还给出了三组更接近实际开发的信号：

- 在 [App Entity / App Intent 跨 OS 兼容帖](https://developer.apple.com/forums/thread/839105)中，开发者说明 iOS 27 Schema 宏会迫使旧部署目标复制 Entity、Intent 和下游类型；Apple DTS 的回复是当前看起来无法由同一类型同时支持两代，并要求继续提交 Feedback。它支持“按 OS/SDK 版本隔离 Binding”，不支持把 Apple 宏放入 JCL Core。
- 在 [Phone Schema 执行帖](https://developer.apple.com/forums/thread/839079)中，Siri 已识别联系人并口头宣布呼叫，但 `perform()` 没有执行；开发者还在楼中楼指出 DTS 首次建议的接口已被文档标为 deprecated，最终仍无确认修复。这证明“解析/播报成功”不等于 `committed`。
- 在 [Foundation Models beta 4 帖](https://developer.apple.com/forums/thread/840236)中，两名开发者分别报告无工具时模型仍索要工具、泄露 JSON 或内部推理样式内容；Apple DTS 只要求最小复现，尚未定性。它是 Beta 风险信号，不是正式版本的普遍结论，但足以要求固定回归集，并让模型输出始终经过 Parser、Schema、Policy 与确认门。

### GitHub SDK 楼中楼：错误分层和双栈迁移不是纸面问题

以下均是实现者缺陷讨论，不等于 MCP 规范本身有相同 Bug；它们的价值在于暴露跨代 Adapter 会怎样失败。

| 讨论 | 楼中楼暴露的问题 | 对 JCL 的修正 |
|---|---|---|
| [Go SDK #1117](https://github.com/modelcontextprotocol/go-sdk/issues/1117) | Issue 提交者报告 `HTTP 400 + 可解码 JSON-RPC error` 被升级成永久连接失败；回复提出“当前调用失败后下一次仍可成功”的回归测试 | 纯分类器先把 `call_error` 与 `transport_error` 分开；真实连接生命周期仍待集成验证 |
| [C# SDK #1765](https://github.com/modelcontextprotocol/csharp-sdk/issues/1765)（已关闭） | Issue 提交者报告 `server/discover` 的 404/400 在 HTTP 层提前抛出，旧 initialize 回退没有机会运行，并在后续更新中补充通道生命周期问题 | 发现不是布尔值；保留原始原因，并在真实 Adapter 中测试回退路径 |
| [Inspector #1807](https://github.com/modelcontextprotocol/inspector/issues/1807) | Issue 提交者报告发现阶段 401/403 被误判为“不支持新协议” | `auth_required` 绝不自动降级为 `discovery_unsupported` |
| [C# SDK #1777](https://github.com/modelcontextprotocol/csharp-sdk/issues/1777) | 提交者描述旧有状态客户端和新无状态客户端在同端点的迁移死锁，并提出 Hybrid 作为兼容方案 | 保留 legacy bridge 与显式版本协商，不一夜硬切 |
| [Conformance #418](https://github.com/modelcontextprotocol/conformance/issues/418) | Issue 提交者报告 Raw HTTP / inline mock 绕开公共 Wire Validation；回复继续指出未覆盖调用点 | 一致性测试必须标记是否经过真实 Registry/Transport/Adapter 路径 |

### Reddit：确认过多同样会破坏安全

在 [46 个云控制工具的 HITL 讨论](https://www.reddit.com/r/mcp/comments/1v9wqi5/our_mcp_server_exposes_a_whole_cloud_platform_46/)中，一方主张每个高后果操作暂停并生成 Receipt；楼中楼反驳“所有写操作都一键确认”会产生确认疲劳，也可能与 Client/HITL Gateway 重复确认。实践者补充：Receipt 不能只有 `200 OK`，还应包含资源 ID、名称和位置。

**JCL 路线修正。** 确认按爆炸半径、不可逆性和数据敏感度分层；一次操作只保留一个 Host 所有的明确 Commit Gate。Receipt 记录具体资源和验证阶段，无法证明现实资源时使用 `committed_unverified` 或 `unknown`。

在 [同名 Capability 发生变化后的授权讨论](https://www.reddit.com/r/mcp/comments/1va0pv4/when_an_mcp_server_changes_do_the_users_existing/)中，主帖与回复指出只绑定工具名、稳定 ID 或 Hash 任一单项都不完整；可操作的最小改进是把规范化定义摘要与授权一起保存，并在每次调用前校验。Jidan 已据此把 Capability 定义指纹纳入 Grant 和 Receipt，但发布者来源与 Adapter 二进制信任仍是待补边界。

## 对 JCL 的具体路线修正

### P0：固定三层边界

| 层 | 负责 | 明确不负责 |
|---|---|---|
| JCL Core / Profile | Capability ID、Schema、Effect/Risk、确认要求、结果状态、Conformance Vectors | MCP Session/Header、Android Permission、Apple Entitlement、模型提示词 |
| Host 权力链 | Policy、TaskPlan、Grant、Commit Gate、幂等、Receipt、安装信任 | 相信模型或 Adapter 自报成功与低风险 |
| Platform Binding | MCP、AppFunctions、App Intents、Intent、Shortcut、Web 的原生翻译与生命周期 | 改写已确认参数、扩大 Scope、签发 Grant |

### P0：把写操作定义为可验证状态机

```text
proposal → validated plan → preview → user grant → execute → receipt
                                      └────────→ deny / expire
execute → succeeded | committed_unverified | outcome_unknown | failed_before_commit
```

高风险操作不能把超时自动重试成成功；`planned`、`opened`、`committed` 和 `unknown` 必须是不同状态。

### P0：扩展现有幂等设计，而不是等待协议统一

- 操作摘要覆盖 Profile/Capability 版本、规范化参数和确认后的 Plan；
- 将来接 MRTR 时，把 `requestState`、`inputResponses` 和每轮确认纳入等价性；
- 相同 Key + 相同摘要返回原结果，相同 Key + 不同摘要在 Handler 前冲突；
- Grant 单次消费与 Provider 幂等必须同时存在：前者约束授权重放，后者约束结果丢失后的执行重放。

### P1：用一致性向量承受协议变化

- 建立 `spec × SDK × Host × transport × Binding × tested_at` 兼容矩阵；
- 增加旧 MCP 与 2026-07-28 的发现、版本拒绝和 Bridge 测试；
- 在多 Validator 上加入 `oneOf`、`$ref`、错误类型和超大 Schema 的负向向量；
- 文件/二进制暂时显式标为不支持，或另建 Artifact Profile，禁止把大段 Base64 塞进模型上下文。

### P1：保持 MCP、A2A 与移动平台的范围分离

边界时间项：一篇于 2026-07-26 23:05 UTC 提交、即北京时间 7 月 27 日的窄场景对比研究认为，MCP 较轻但把会话状态和任务生命周期留给应用；A2A 的多轮任务抽象更丰富，代价是更高复杂度。作者明确没有宣称普遍优劣。[MCP 与 A2A 对比论文](https://arxiv.org/abs/2607.23884)

JCL 因此只覆盖“意图/Agent 到动作能力”这条边，不吞并 Agent-to-Agent 协商、长任务编排或 UI Runtime。

## 已落地 / 待落地清单

### 已落地于本仓库

- [x] 与 MCP Tool 兼容、但不绑定 MCP transport 的 [`message.compose` Profile](../profiles/message.compose.tool.json)。
- [x] `TaskPlan → Policy → Grant → Runtime → Receipt` Host 权力链；Grant 绑定精确 Plan Hash。
- [x] SQLite 持久 Grant Ledger，Nonce 原子单次消费，拦截进程重启后的授权重放。
- [x] Host 自有的 `handoff_planned` / `handoff_opened` 和 `committed_unverified` / `outcome_unknown` 语义；Adapter 不能冒充现实成功。
- [x] 哈希链 Receipt Log 与篡改检测。
- [x] 新签 Grant 强制绑定 Capability 规范化定义指纹；同名 Schema、Effect、确认规则或 Adapter ID 变化会在执行前拒绝，Receipt 记录实际指纹。
- [x] Discovery 纯分类器与单元测试：401/403、裸 404、可解码的单次 JSON-RPC Error、协议畸形与传输失败分别处理；分类结果不会把单次调用错误编码成永久失败。真实连接生命周期、版本探测与回退集成仍待实现。
- [x] 受控 Android AppFunctions Memo Provider：写后读回、Provider 幂等、旧操作重放和 Key 冲突验证。
- [x] Android / 微信真实 Picker 交接验证：不选择联系人、不点击发送。
- [x] Nine Lights 的 Python Host 与独立 JavaScript Host 共享 Profile 和一致性向量，不冒充共享 Runtime。
- [x] Pinyin Frontend 0.1 已冻结为无权限输入实验，不再扩张成 JCL 语言。

### 待落地，按优先级

- [ ] MCP 2026-07-28 真正的 Client/Server Adapter、旧版 Bridge 与跨 Host 兼容矩阵。
- [ ] 将现有操作摘要扩展到 MRTR continuation state，并加入“同 Key、不同 continuation”负例。
- [ ] 在已落地的 Capability 定义指纹之上，继续补 Adapter 二进制/发布者来源 Pinning；是否采用签名 Manifest，等待协议与信任模型成熟后再决定。
- [ ] JSON Schema 组合关键字的跨 Python、AJV、Kotlin/Java、Swift Validator 敌对一致性套件。
- [ ] 真实 Apple App Intents Binding 与设备证据；在公共 entitlement 不可用时验证 Shortcut / Share Sheet 降级。
- [ ] 文件与二进制 Artifact Profile，明确大小、传输、内容类型、哈希和用户披露边界。
- [ ] 至少一个非 Android 的真实写入或 Handoff Binding；在此之前不宣称“移动端通用”。
- [ ] 把兼容性声明做成机器可读证据，而不是 README 中的笼统徽章。

## 最终裁决

七日动态没有推翻 JCL，反而淘汰了它最容易走偏的部分：

> **JCL 不做 AI 的新编程语言，也不做第二个 MCP。它应成为 MCP、Android 与 Apple 之上的最薄动作语义层；开放的是实现和共创，收紧的是授权、提交与现实结果。**
