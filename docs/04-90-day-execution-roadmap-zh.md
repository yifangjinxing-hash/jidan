# Jidan 90 天执行路线图

> 决策日期：2026-08-01。目标不是做一段“能点手机”的演示，而是证明一种可迁移的系统原语：目标 → 受约束任务图 → 最小授权 → 确定性执行 → 可验证回执。

## 2026-08-02 历史镜鉴修正

C/UNIX、JVM、Web 和容器真正反复证明的是“稳定接口让实现者吸收差异”，不是“所有平台最终共用同一种语言、ABI、Runtime 或 UI”。本路线因此把冻结对象从公共 JGraph/共享实现改为 **JCL 的外部可观察语义、Profile 版本与 conformance fixtures**；JGraph 继续是 Host 内部实现。自然语言只能产生无权限 Proposal；Pinyin Frontend 0.1 已于 2026-08-02 冻结归档，只保留兼容与复现，不再扩展语法或别名。依据见[历史镜鉴与路线护栏](06-history-lessons-and-route-guardrails-zh.md)。

路线顺序调整为：

```text
薄 JCL 契约与一致性 → 可替换 Frontend → Host 权力边界
                     → 平台原生 Binding → 人类 Commit 与真实用户验证
```

## 路线裁决

### Phase 1 执行锁（2026-08-01）

本阶段推进两条共用同一 Runtime 的官方通路：用 ADB/Shell 验证 `cmd app_function`、能力契约、JGraph、授权和回执；同时准备 Android 17 AppFunctions Agent Access 的 EAP/OEM 准入材料。Shizuku/Root 仅保留为可替换实验桥，不并入主程序；Accessibility/MediaProjection 兼容层继续冻结。

原先的三条路线保留，但重新排序和定性：

| 轨道 | 定位 | 现在做什么 | 明确不做什么 |
|---|---|---|---|
| ADB / Shell Lab | 两周内验证 Android 17 AppFunctions 的真实能力 | 先使用官方 `adb shell cmd app_function`，打通发现、执行、解析、超时、审计；随后再评估 Shizuku UserService | 不把开发者模式、无线调试或 shell 身份宣传为大众产品能力 |
| Stock APK / Agent Access | 新增的官方第三路 | 固定包名与长期签名；实现逐目标授权状态机草案；准备 AppFunctions EAP/OEM allowlist 申请材料 | 不宣称当前公共 SDK 已开放，不绕过设备 allowlist |
| AOSP / OEM Core | 长期系统级产品线 | Cuttlefish 上的平台签名 broker、AppFunctions、受限 GUI 控制、SELinux、系统确认与回执 | 首版不改 Linux、GKI、HAL、驱动，不把 planner 放进 `system_server` |

这三条不是三个产品。它们对外共用 JCL Profile、结果语义和一致性夹具；内部可以复用当前 JGraph、授权策略与回执实现，但第三方 Host 不必采用同一 Runtime 或源代码，执行后端也保持平台原生。

## 第 0–14 天：证明 Shell 闭环

### 必须交付

1. 固定 Android 17 / API 37 真机或模拟器版本，并记录 build fingerprint。
2. 安装两个由团队控制、暴露 AppFunctions 的 reference app。
3. 使用官方命令完成并留存原始输出：

   ```text
   adb shell cmd app_function list-app-functions
   adb shell cmd app_function execute-app-function ...
   ```

4. 让 Jidan 适配器完成：设备探测、函数发现、参数 JSON 编码、执行、错误分类、超时、敏感字段脱敏和不可变审计记录。
5. 把适配器接入现有 JGraph runtime；模型仍只能输出计划，不能拼接或执行任意 shell 字符串。
6. 做五组负向测试：无设备、多个设备、权限拒绝、函数不存在、畸形/超大参数。
7. 对每个目标包先执行语义面探测：`AppFunctions > RemoteInput > person-bound shortcut > blocked`；OCR/坐标不得成为收件人身份依据。
8. 用同一份 `message.compose` Profile 生成 Android、iOS、Web 数据计划；上层调用不得包含平台字段，自然语言/拼音字段不得进入能力 Schema，Web 计划不得冒充原生 UI 已打开。
9. 用 Nine Lights 作为离线一致性尖峰：Python Host 走完整 Runtime/Receipt，独立 Web JavaScript Host 重放同一组向量；只据此陈述“共享语义”，不得宣传为共享 Runtime 或移动端通用游戏。

### 第 14 天 Go / No-Go 门槛

- 在固定设备上连续完成 30 次“读 → 转换 → 可撤销写入”，至少 27 次成功。
- 未确认前零副作用；重试不产生重复写入。
- shell 适配器没有通用命令入口，只允许 `app_function` 的固定参数化子命令。
- 日志可证明实际调用了哪个设备、包、函数和参数摘要。
- `message.compose` 的 Profile、Runtime 导出和 conformance vector 完全一致；三个计划 Binding 对公共结果状态的解释一致。
- Nine Lights 的 Python 与 JavaScript 实现通过同一组 start、press 和解法向量；任一端特判向量或共享规则实现均不算独立证据。
- 若直接 ADB 没跑通，不进入 Shizuku 集成；先修清真实平台问题。

### Shizuku 实验的进入条件

只有直接 ADB 闭环通过后才做，并放在独立分支/模块：

- 使用 UserService，使受审计的最小代码在 UID 2000 下运行；不使用任意 `newProcess` 命令台。
- 对候选实现做源码、提交历史、发布签名、许可证、依赖和更新机制审计。
- 在 Android 16、Android 17，至少两家 OEM 上分别验证 ADB 与 root 启动模式。
- 失败时自动退回“连接电脑运行官方 ADB”，不静默换 fork。
- 不捆绑、重签或要求用户卸载官方 Shizuku，除非经过单独安全评审和明确同意。

## 第 15–42 天：冻结薄腰与一致性，不冻结统一 Runtime

### JCL 与 Runtime

- 冻结 JCL 0.1 的 capability ID、输入/输出 Schema、风险与公共结果语义；发布 conformance vectors 和最小 Adapter Kit。
- JGraph 保持 Host 内部、可演进、可替换；当前 Runtime 仍可使用 `Read / Transform / Branch / Call / Confirm / Wait / Verify / Compensate / Emit / Handoff`，但不把它变成生态必学 DSL。
- 内部节点继续强制声明 effect、输入输出 schema、幂等键、超时、重试、验证和补偿。
- planner 与执行器完全分权；执行器拒绝任意 shell、任意 Intent、任意包名和未注册 URI。
- SQLite/Proto 持久化检查点；杀进程、断网和重启后继续，已提交节点不重复执行。
- HMAC 开发密钥替换为 Android Keystore；有 StrongBox 时记录硬件保证等级。
- 所有公开 Demo 必须经过 TaskPlan、Grant、Confirmation、Runtime 和 Receipt；直接 Registry 调用只允许出现在明确标注的 Adapter conformance test 中。
- 至少让一名非核心开发者在不修改 Runtime 的前提下完成一个计划型 Binding 并跑过一致性测试。
- Pinyin Frontend 保持冻结：兼容性修复和安全回归可以合入，不新增语法、别名、模糊匹配或新的活跃入口。

### AOSP

- AOSP 是条件性并行轨：第 14 天的 JCL 契约 Gate 未通过，或外部 Binding 仍必须修改 Runtime 时，不扩大系统集成投入。
- 基于固定 AOSP 17 tag 构建 Cuttlefish。
- broker 先做成 `system_ext` 的平台签名 privileged app，通过自定义 signature AIDL 暴露窄接口。
- planner 是另一个普通 UID；负向测试证明它不能直接调用 AppFunctions 或 Computer Control。
- 完成 privapp allowlist、Assistant role、导出组件和 SELinux default-deny 配置。

### Reference apps

由团队控制四个最小 AppFunction，避免把第三方生态覆盖误当作平台已具备：

- `create_event`
- `create_reminder`
- `create_note`
- `compose_message`

消息只能生成草稿或打开预填充编辑页，绝不自动发送。

## 第 43–70 天：黄金流程与失败语义

黄金流程：

> 从用户主动提供的群聊截图或语音中提取会议，创建日历事件和提醒，保存议程，并生成确认消息草稿。

验收范围：

- 30 个截图/语音 golden case，所有时间、时区、联系人歧义都可编辑。
- 先展示完整计划和影响，再进行一次计划级授权；外部通信仍在最终提交点单独确认。
- 为各端实现信息结构一致、UI 原生的 Action Card：显示能力、资源、风险、可编辑参数、保证等级和当前现实状态；不强制 Android、Apple、Web 共用 UI Runtime。
- 至少验证一个非 Android 的真实可编辑 Binding；若 Apple/Web 尚只有数据计划，必须继续标为 `handoff_planned`。
- 做至少 10 次目标用户测试，用户必须能分清 UI 概念“已规划、已打开、已提交与结果未知”；机器接口继续使用各层已经定义的精确 token。
- 每一步独立读回验证，显示部分成功、失败、可撤销期限和补偿结果。
- 对屏幕、邮件和 AppFunction 描述中的 prompt injection 做测试；不可信文本不能增加权限或改变策略。
- 一个自有 fixture app 用受限 GUI 路径完成表单填写；验证码、支付、密码、`FLAG_SECURE` 和安全设置立即交给用户。

## 第 71–90 天：产品证据，而非概念视频

### 真机矩阵

至少覆盖三档设备：

- Pixel / 原生 Android 17 基线；
- 一台主流 OEM Android 17；
- 一台中端设备，用于内存、热和电量边界。

分别测量首 token、完整 JGraph 生成、端到端任务时延、峰值/常驻内存、温升、热降频和日均增量耗电。Cuttlefish 结果不得替代 NPU 与功耗数据。

### 发布物

- 可重复构建的 Jidan runtime 与 AOSP 集成说明。
- JCL 0.1 Profile、conformance runner、最小 Adapter Kit 和四个 reference app；Host 内部 JGraph schema 作为参考实现而非公共必选 DSL。
- 公开的能力/设备兼容矩阵，区分 AppFunctions、Intent、确定性 skill、GUI 和用户接管。
- 威胁模型、权限清单、回执示例、失败案例和已知限制。
- 3 分钟演示只展示真实路径，并在界面标出当前执行后端与保证等级。

### 第 90 天 Gate

- 黄金流程 30 次至少 27 次完整成功。
- 零错误收件人、零静默发送、零重复写入。
- 取消后不再启动新节点；崩溃恢复不重复提交。
- 1,000 个畸形或越权 JGraph 全部被拒绝且零副作用。
- 一名非核心贡献者能在一个工作日内完成新 Binding，并在不修改 Runtime 的情况下通过一致性测试。
- 至少 8/10 名目标用户无需培训即可完成黄金流程，并正确判断最终动作是否真的提交。
- 至少一个非 Android Binding 具有真实可复验证据；否则跨平台能力只能标为数据计划。
- AOSP 冷启动后无需 `adb root` 或手工补丁。
- 若开发者接入或目标式交互 Gate 未通过，AOSP/OEM 保持实验轨，不升级为主产品路线。
- 如果 GUI 路径未跑通官方 Computer Control，只能称为“语义执行原型”，不能宣称通用 App 接管。

## 立即砍掉的范围

- 通用 GUI Agent 或“支持所有 App”的承诺。
- 普通商店 APK 的自主 Accessibility Agent。
- 自动发送、支付、删除、安装和系统安全设置。
- 全天候运行的大模型、自训练端侧模型和自造网络协议。
- 把自然语言或拼音定义成公共协议、字节码或机器底层。
- 强制所有 Host 使用同一 JGraph Runtime、UI 框架或共享 C++ Core。
- 把 C ABI 作为万能跨平台能力层，或另造必须降维到 C/汇编的新编译塔。
- 用 WebView、浏览器桥或容器宣称已经获得原生 OS、联系人或跨 App 权限。
- `sharedUserId="android.uid.system"` 捷径。系统权限应使用平台签名、privapp allowlist、角色、窄 AIDL 和 SELinux 明确配置。

## 北极星与护城河

北极星不是点击成功率，而是 **Verified Goal Completion Rate**：用户接受的目标中，完成且有独立证据的比例。必须按原生能力、Intent、确定性 skill、GUI 和用户接管分桶统计。

真正可积累的资产是：跨版本兼容图、类型化能力契约、用户拥有的来源化记忆、任务级最小授权、幂等/补偿知识和可验证回执。模型会迅速商品化，这些不会。
