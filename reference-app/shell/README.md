# Jidan Shell 0.2：Android「手 + 脑」实验版

Jidan Shell 是可安装的独立 Android APK，但还不是独立 ROM 或完整 Jidan OS。

这版第一次接通了真正的无障碍动作链：Jidan 读页面、做计划、一次执行一步、重新读取页面、核验结果，再写本机哈希回执。

![手脑实验完成画面](../../docs/assets/jidan-hand-brain-lab-0.2.png)

## 现在能玩什么

首页有三个快捷动作：

- **打开支付宝**：只打开固定包名的应用入口，不传收款人、金额、密码或验证码，也不声称已经付款。
- **打开按键精灵**：只打开经过固定包名、签名身份和版本检查的 APK 前门，把它当作“候选的手”供人观察；不调用它的私有服务、Socket 或脚本接口，也不把它直接认定为 Jidan 执行器。
- **手 + 脑实验**：打开通过固定包名、签名身份、版本和实验契约检查的自有无网络 APK，自动完成“假收款人 → 假金额 → 假密码 → 假验证码 → 假提交”五步，并核验每一步。

“打开系统设置”仍可在命令框里键入或说出，但不是首页快捷按钮。

语音按钮会调用手机当前的语音识别服务，把识别结果放入同一个命令框。是否联网由手机安装的语音服务决定。

## 怎么安装和试玩

要求 Android 8.0（API 26）或更高版本。两个 APK 不必来自同一次编译，但必须使用匹配的受信签名；实验包的固定版本和实验契约也必须与 Shell 的预期一致。最省事的方式是使用同一个 CI artifact 中提供的成对 APK。

```powershell
adb install -r -t .\reference-app\accessibility-sandbox\build\outputs\apk\debug\accessibility-sandbox-debug.apk
adb install -r -t .\reference-app\shell\build\outputs\apk\debug\shell-debug.apk
```

然后：

1. 打开 **Jidan Shell**；
2. 点 **手 + 脑实验**；
3. 需要授权时会跳到 Android 无障碍设置，请亲自打开 **鸡蛋辅助操作**；
4. 返回 Shell；服务就绪时会自动继续，不需要再确认同一件事；
5. 看到“实验完成：外部交易 0 笔”。

大多数设备只在第一次需要系统无障碍授权；Android 或手机厂商以后仍可能停用服务，届时需要重新开启。Jidan 不会另加一张同义确认卡。

## 这条实验为什么不是假动画

- 页面动作由真实 `AccessibilityService` 执行，不是 Shell 自己改一行成功文字；
- 执行器只按稳定的资源 ID 找节点，不使用屏幕坐标；
- 每一步之后都重新读取页面，并核对一个预先写进计划的后置条件；
- 系统接收了动作、但页面变化无法核验时，结果是 `outcome_unknown`，而且不会自动重试；
- 每个动作先写并同步一条 `PREPARED`，再写一条 `RESULT`；回执记录动作类型、前后页面摘要、系统是否接收、结果是否核验和前一条回执哈希；
- 假密码和假验证码只在当前运行内存里短暂出现；它们的原文不会写进 Jidan 计划、回执或实验应用存储，提交后页面字段立即清空。

实验室自身没有 `INTERNET` 权限，也没有账户、订单或支付 SDK。Shell 还会检查固定包名、签名身份、版本、实验契约与可调试标志；不满足就直接阻断，不会假装进入一个已经可用的 SHADOW 执行通道。

## 构建和测试

使用 JDK 17 和 Android SDK 37：

```powershell
cd reference-app
.\gradlew.bat --no-daemon `
  :shell:testDebugUnitTest `
  :shell:assembleDebug `
  :shell:lintDebug `
  :accessibility-sandbox:assembleDebug `
  :accessibility-sandbox:lintDebug
```

输出文件：

- `reference-app/shell/build/outputs/apk/debug/shell-debug.apk`
- `reference-app/accessibility-sandbox/build/outputs/apk/debug/accessibility-sandbox-debug.apk`

## 目前清楚的边界

- 当前 Android 执行器只订阅 `dev.jidan.accessibility.sandbox`，不会常驻读取其他 App。
- `android.ui.shadow_plan` 目前只是能表达真实 App 步骤的规格契约；Android 侧真实 App 观察器和执行器都没有接入。
- 支付、密码和验证码能力没有从协议删除；它们先在合成实验里完整执行。真实 App 目前没有可运行的规划或执行通道，只保留未来人工接管的契约边界。
- “无障碍开关亮着”不等于服务健康；当前已有本轮会话的首帧超时与短时租约，跨厂商长期心跳、失效恢复和节点树缺失体验仍要继续完善。
- JCL 文件采用 MCP 兼容的 Tool 形状，但当前 Android“手”只通过内部 Kotlin 映射运行，没有对外注册 MCP 或 JSON 执行端点。
- Jidan 仍不是默认桌面，也没有 AOSP、驱动或系统级安全域；这不是完整操作系统。

完整设计、APK 静态审计和社区踩坑依据见[《Android 手 + 脑实验》](../../docs/10-android-hand-brain-lab-zh.md)。
