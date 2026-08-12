# Nine Lights（九灯）：一次“共享语义，不共享 Runtime”的小游戏尖峰

> 状态：实验性一致性探针。它用于检验 JCL 0.1 的能力契约能否被两个独立 Host 实现，不是新的游戏编程语言，也不是“所有平台已经通用”的产品声明。

## 为什么先做一个小游戏

`message.compose` 可以检验权限、交接和现实结果，但跨端验证会受到系统 API、设备权限和原生 UI 的影响。Nine Lights 刻意选择一个离线、确定性、没有现实副作用的规则系统，把问题缩小为：

> 给定同一个能力 ID、JSON Schema 和输入状态，两个不共享 Runtime 源码的 Host，能否得到同一个可观察结果？

如果答案是肯定的，证明的是 **Profile 与一致性向量可以形成窄兼容层**。它不证明 Python、JavaScript、Android 和 iOS 应该使用同一个 Runtime，也不证明 JCL 是一种通用编程语言。

## 玩法

棋盘是 3 × 3 的九盏灯。按下一格，会翻转它自己以及相邻的上、下、左、右灯；让全部灯熄灭即获胜。

内置三关均为固定、可复现的初始状态：

- `cross`：十字亮灯；一步解为 `5`；
- `corners`：左上与右下两个拐角簇亮灯；示例解为 `1,9`；
- `full`：九灯全亮；示例解为 `1,3,5,7,9`。

命令行使用人类习惯的 `1–9` 编号；机器契约中的 `cell` 使用 `0–8`。这个差异由 Host 输入层负责，不能偷偷进入公共 Profile。

## 两个薄能力

Nine Lights 不把整场游戏塞进一个有状态会话。状态完整地随每次请求传入和返回：

| Capability | 输入 | 输出 | 效果语义 |
|---|---|---|---|
| `game.ninelights.start` | `levelId` | 初始 `state` | `READ / COMPUTE / STATELESS` |
| `game.ninelights.press` | 完整 `state` + `cell` | 新 `state` | `READ / COMPUTE / STATELESS` |

对应机器契约位于：

- [`game.ninelights.start`](../profiles/game.ninelights.start.tool.json)
- [`game.ninelights.press`](../profiles/game.ninelights.press.tool.json)
- [跨实现一致性向量](../profiles/conformance/game.ninelights.vectors.json)

规则实现必须拒绝字段互相矛盾的状态、终局后的继续操作、越界格子和多余字段。当前尖峰不提供状态来源认证，也不证明任意输入棋盘都由某个初始关卡合法演进而来。因为它只计算新数据，不触碰设备、网络、文件或其他人的资源，所以无需人工确认；这不意味着现实世界的 `WRITE`、`EXTERNAL` 或 `IRREVERSIBLE` 能力可以跳过确认。

## Python Host：走完整 Jidan 链

从 `prototype/` 运行：

```powershell
python ninelights_demo.py
python ninelights_demo.py --level cross --moves 5
python ninelights_demo.py --level corners --moves 1,9
python ninelights_demo.py --level full --moves 1,3,5,7,9 --json
```

Python CLI 的每次 `start` 或 `press` 都重新构造 `TaskPlan`、签发最小 `READ` Grant、通过 `JidanRuntime` 调用已注册能力，并追加哈希链 Receipt。它没有为了演示而直接调用 Registry。脚本输出中的 `receiptCount`、`lastReceiptHash` 与 `receiptChainVerified` 只描述这条 Python Host 执行链。

## Web Host：独立 JavaScript 实现

[`prototype/web/ninelights.html`](../prototype/web/ninelights.html) 是无第三方依赖的独立 JavaScript Host。它不调用 Python，也不运行 `JidanRuntime`；浏览器 UI 和本地状态管理属于 Web Host 自己。

```powershell
node prototype/tools/check_ninelights_web.js
```

检查脚本让 JavaScript 实现重放同一份 [`game.ninelights.vectors.json`](../profiles/conformance/game.ninelights.vectors.json)。因此目前能够陈述的证据是：

```text
同一 JCL Profile + 同一组输入/预期输出
        ├─ Python Host：JidanRuntime + Receipt
        └─ Web Host：独立 JavaScript 规则实现
                         ↓
                 通过同一一致性向量
```

Web 路径没有冒充 Python 的 Grant、Receipt 或设备权限。两端共享的是能力 ID、Schema、状态语义和测试向量，不是实现代码或 Runtime。

## 这次尖峰证明了什么

- 纯计算能力可以保持无状态，请求可独立路由、记录和重放测试；
- Profile 不含平台、UI 或编程语言字段，同一契约可以由独立 Host 实现；
- 一致性向量比“用了同一种语言”更能约束外部可观察行为；
- Python 完整 Runtime 与轻量 Web Host 可以共存，而不把 JGraph 变成公共 DSL。

## 尚未证明什么

- 没有 Android、iOS、HarmonyOS 或 Windows 原生实现证据；
- 没有网络多人、账户、同步、反作弊、存档迁移或无障碍验收；
- Web Host 没有复刻 Python 的授权账本与 Receipt 链；
- 一个九格确定性游戏不能代表复杂业务、外部副作用或长期任务已经跨端兼容；
- 这不是“用自然语言或拼音写游戏”，也不依赖已冻结的拼音 Frontend。

下一步只有在独立实现持续通过相同向量、错误语义也一致时，才考虑增加新的游戏规则或原生 Host；不为展示数量扩张 Profile。
