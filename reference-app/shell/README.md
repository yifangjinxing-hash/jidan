# Jidan Shell 0.3：Android 小事清单 +「手脑」实验版

Jidan Shell 是可安装的独立 Android APK，但还不是独立 ROM 或完整 Jidan OS。

这版把真正的无障碍动作链从合成实验推进到一件可用的小事：Jidan 能从 Shell 打开自有清单 App，填写一句待办、同步保存、重新读取页面核验结果，再返回 Shell。五步合成实验仍保留用于敏感动作故障测试。

<p align="center">
  <img src="../../docs/assets/jidan-shell-daily-complete-0.3.png" alt="Jidan Shell 0.3 在 Android 17 模拟器完成跨 App 记小事" width="360" />
  <img src="../../docs/assets/jidan-daily-list-0.1.png" alt="小事清单重新打开后事项仍存在" width="360" />
</p>

## 现在能玩什么

首页有三个快捷动作：

- **打开支付宝**：只打开固定包名的应用入口，不传收款人、金额、密码或验证码，也不声称已经付款。
- **打开按键精灵**：只打开经过固定包名、签名身份和版本检查的 APK 前门，把它当作“候选的手”供人观察；不调用它的私有服务、Socket 或脚本接口，也不把它直接认定为 Jidan 执行器。
- **记小事**：执行“记下明天买鸡蛋”，打开同签名、固定版本、固定契约且无网络的自有清单 App，由内置无障碍手填写、保存、重新核验并返回 Shell。

“打开系统设置”和“开始手脑实验”仍可在命令框里键入或说出，但不是首页快捷按钮。

语音按钮会调用手机当前的语音识别服务，把识别结果放入同一个命令框。是否联网由手机安装的语音服务决定。

## 怎么安装和试玩

要求 Android 8.0（API 26）或更高版本。三只 APK 必须使用匹配的受信签名；两个目标 App 的固定版本和实验契约也必须与 Shell 的预期一致。最省事的方式是使用同一个 CI artifact 中提供的整套文件，并按下面顺序安装：

```powershell
adb install -r -t .\reference-app\daily-demo\build\outputs\apk\debug\daily-demo-debug.apk
adb install -r -t .\reference-app\accessibility-sandbox\build\outputs\apk\debug\accessibility-sandbox-debug.apk
adb install -r -t .\reference-app\shell\build\outputs\apk\debug\shell-debug.apk
```

### 先玩一件真实小事

1. 打开 **Jidan Shell**；
2. 点 **记小事**；
3. 需要授权时会跳到 Android 无障碍设置，请亲自打开 **鸡蛋辅助操作**；
4. 返回 Shell；服务就绪时会自动继续，不需要再确认同一件事；
5. 鸡蛋会打开**小事清单**、写入“明天买鸡蛋”、保存并核验，然后自动返回；
6. Shell 显示“已经记下”。你也可以从桌面单独打开**小事清单**，完成、撤销或清空已完成事项。

大多数设备只在第一次需要系统无障碍授权；Android 或手机厂商以后仍可能停用服务，届时需要重新开启。Jidan 不会另加一张同义确认卡。

### 再玩合成手脑实验

在输入框键入或说出“开始手脑实验”。它会打开通过固定包名、签名、版本和契约检查的无网络实验 APK，自动完成“假收款人 → 假金额 → 假密码 → 假验证码 → 假提交”五步。首次授权流程与上面相同。

## 这只手为什么不是假动画

- 页面动作由真实 `AccessibilityService` 执行，不是 Shell 自己改一行成功文字；
- 执行器只按稳定的资源 ID 找节点，不使用屏幕坐标；
- 每一步之后都重新读取页面，并核对一个预先写进计划的后置条件；
- 系统接收了动作、但页面变化无法核验时，结果是 `outcome_unknown`，而且不会自动重试；
- 每个动作先写并同步一条 `PREPARED`，再写一条 `RESULT`；回执记录动作类型、前后页面摘要、系统是否接收、结果是否核验和前一条回执哈希；
- 小事清单使用同步本机提交；同一个 `requestId` 重放不会再新增一条，换了正文的重放会被拒绝；
- 清单正文只由小事清单 App 本地保存，Shell 与无障碍回执只保留摘要；
- 合成实验中的假密码和假验证码只在当前运行内存里短暂出现；原文不会写进 Jidan 计划、回执或实验应用存储，提交后页面字段立即清空。

小事清单和合成实验室都没有 `INTERNET` 权限。Shell 会检查固定包名、签名身份、版本、实验契约与可调试标志；不满足就直接阻断，不会假装进入一个已经可用的第三方执行通道。

## 构建和测试

使用 JDK 17 和 Android SDK 37：

```powershell
cd reference-app
.\gradlew.bat --no-daemon `
  :shell:testDebugUnitTest `
  :shell:assembleDebug `
  :shell:lintDebug `
  :daily-demo:testDebugUnitTest `
  :daily-demo:assembleDebug `
  :daily-demo:lintDebug `
  :accessibility-sandbox:assembleDebug `
  :accessibility-sandbox:lintDebug
```

输出文件：

- `reference-app/shell/build/outputs/apk/debug/shell-debug.apk`
- `reference-app/daily-demo/build/outputs/apk/debug/daily-demo-debug.apk`
- `reference-app/accessibility-sandbox/build/outputs/apk/debug/accessibility-sandbox-debug.apk`

## 目前清楚的边界

- 当前 Android 执行器只订阅 `dev.jidan.daily.demo` 与 `dev.jidan.accessibility.sandbox` 两个自有包，不会常驻读取其他 App。
- `daily.note.create` 只允许写入自有、本地、可撤销的小事清单；它不等于任意 App 自动化。
- `android.ui.shadow_plan` 目前只是能表达真实 App 步骤的规格契约；Android 侧真实 App 观察器和执行器都没有接入。
- 支付、密码和验证码能力没有从协议删除；它们先在合成实验里完整执行。真实第三方 App 目前没有可运行的规划或执行通道，只保留未来人工接管的契约边界。
- “无障碍开关亮着”不等于服务健康；当前已有本轮会话的首帧超时与短时租约，跨厂商长期心跳、失效恢复和节点树缺失体验仍要继续完善。
- JCL 文件采用 MCP 兼容的 Tool 形状，但当前 Android“手”只通过内部 Kotlin 映射运行，没有对外注册 MCP 或 JSON 执行端点。
- Jidan 仍不是默认桌面，也没有 AOSP、驱动或系统级安全域；这不是完整操作系统。

普通人上手见[《三分钟实战：让鸡蛋跨 App 记下一件小事》](../../docs/11-daily-note-cross-app-hand-zh.md)；完整设计、APK 静态审计和社区踩坑依据见[《Android 手 + 脑实验》](../../docs/10-android-hand-brain-lab-zh.md)。
