# Jidan 90 天执行路线图

> 决策日期：2026-08-01。目标不是做一段“能点手机”的演示，而是证明一种可迁移的系统原语：目标 → 受约束任务图 → 最小授权 → 确定性执行 → 可验证回执。

## 路线裁决

### Phase 1 执行锁（2026-08-01）

本阶段只推进官方 ADB/Shell 通路：`cmd app_function` 动态代理、能力契约归一化、JGraph 调度、计划级授权和回执。Shizuku/Root 仅保留为闭环通过后的可替换实验桥，不并入主程序；Google Play 上架、AAPM 对策、Accessibility/MediaProjection 兼容层全部冻结，不再占用 Phase 1 工程资源。

原先的三条路线保留，但重新排序和定性：

| 轨道 | 定位 | 现在做什么 | 明确不做什么 |
|---|---|---|---|
| ADB / Shell Lab | 两周内验证 Android 17 AppFunctions 的真实能力 | 先使用官方 `adb shell cmd app_function`，打通发现、执行、解析、超时、审计；随后再评估 Shizuku UserService | 不把开发者模式、无线调试或 shell 身份宣传为大众产品能力 |
| Stock APK / Play | 冻结，不属于 Phase 1 | 不投入开发和政策研究 | 不做 Accessibility/MediaProjection 兼容桥，不以商店上架约束当前原型 |
| AOSP / OEM Core | 真正的系统级产品主线 | Cuttlefish 上的平台签名 broker、AppFunctions、受限 GUI 控制、SELinux、系统确认与回执 | 首版不改 Linux、GKI、HAL、驱动，不把 planner 放进 `system_server` |

这三条不是三个产品。它们共用 JGraph、JCC、授权策略、适配器接口和回执格式，只有执行后端不同。

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

### 第 14 天 Go / No-Go 门槛

- 在固定设备上连续完成 30 次“读 → 转换 → 可撤销写入”，至少 27 次成功。
- 未确认前零副作用；重试不产生重复写入。
- shell 适配器没有通用命令入口，只允许 `app_function` 的固定参数化子命令。
- 日志可证明实际调用了哪个设备、包、函数和参数摘要。
- 若直接 ADB 没跑通，不进入 Shizuku 集成；先修清真实平台问题。

### Shizuku 实验的进入条件

只有直接 ADB 闭环通过后才做，并放在独立分支/模块：

- 使用 UserService，使受审计的最小代码在 UID 2000 下运行；不使用任意 `newProcess` 命令台。
- 对候选实现做源码、提交历史、发布签名、许可证、依赖和更新机制审计。
- 在 Android 16、Android 17，至少两家 OEM 上分别验证 ADB 与 root 启动模式。
- 失败时自动退回“连接电脑运行官方 ADB”，不静默换 fork。
- 不捆绑、重签或要求用户卸载官方 Shizuku，除非经过单独安全评审和明确同意。

## 第 15–42 天：冻结 Jidan 的新系统原语

### Runtime

- 冻结 JGraph v0：`Read / Transform / Branch / Call / Confirm / Wait / Verify / Compensate / Emit / Handoff`。
- 每个节点强制声明 effect、输入输出 schema、幂等键、超时、重试、验证和补偿。
- planner 与执行器完全分权；执行器拒绝任意 shell、任意 Intent、任意包名和未注册 URI。
- SQLite/Proto 持久化检查点；杀进程、断网和重启后继续，已提交节点不重复执行。
- HMAC 开发密钥替换为 Android Keystore；有 StrongBox 时记录硬件保证等级。

### AOSP

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
- JCC/JGraph v0 schema、SDK 和四个 reference app。
- 公开的能力/设备兼容矩阵，区分 AppFunctions、Intent、确定性 skill、GUI 和用户接管。
- 威胁模型、权限清单、回执示例、失败案例和已知限制。
- 3 分钟演示只展示真实路径，并在界面标出当前执行后端与保证等级。

### 第 90 天 Gate

- 黄金流程 30 次至少 27 次完整成功。
- 零错误收件人、零静默发送、零重复写入。
- 取消后不再启动新节点；崩溃恢复不重复提交。
- 1,000 个畸形或越权 JGraph 全部被拒绝且零副作用。
- AOSP 冷启动后无需 `adb root` 或手工补丁。
- 如果 GUI 路径未跑通官方 Computer Control，只能称为“语义执行原型”，不能宣称通用 App 接管。

## 立即砍掉的范围

- 通用 GUI Agent 或“支持所有 App”的承诺。
- 普通商店 APK 的自主 Accessibility Agent。
- 自动发送、支付、删除、安装和系统安全设置。
- 全天候运行的大模型、自训练端侧模型和自造网络协议。
- `sharedUserId="android.uid.system"` 捷径。系统权限应使用平台签名、privapp allowlist、角色、窄 AIDL 和 SELinux 明确配置。

## 北极星与护城河

北极星不是点击成功率，而是 **Verified Goal Completion Rate**：用户接受的目标中，完成且有独立证据的比例。必须按原生能力、Intent、确定性 skill、GUI 和用户接管分桶统计。

真正可积累的资产是：跨版本兼容图、类型化能力契约、用户拥有的来源化记忆、任务级最小授权、幂等/补偿知识和可验证回执。模型会迅速商品化，这些不会。
