# Jidan

**一个围绕能力契约、任务图、明确授权与可验证回执构建的轻量、多语种 Android 智能体运行时。**

[English](README.md) · [语言与翻译](docs/i18n/README.md) · [参与贡献](CONTRIBUTING.md) · [安全说明](SECURITY.md)

> 当前是实验原型。Jidan 不是完整的 Android 发行版，不是提权或破解工具，也不是可直接托管重要事务的生产助手。请只在受控 App、测试设备和可丢弃数据上使用。

## 为什么做 Jidan

现在的手机让一个简单目标穿过臃肿 App、页面、广告和彼此隔离的生态。Jidan 尝试把软件的最小单位换成：

```text
用户目标
  → 语义动作
  → 能力契约
  → 任务图
  → 策略与确认
  → 适配器执行
  → 可验证回执
```

规划器输出始终按不可信数据处理。只有 schema、scope、effect、授权和确认要求全部通过，能力才会执行。

## 仓库内容

- `prototype/`：无第三方依赖的 Python 能力内核、策略门、任务图 Runtime、持久授权账本、哈希链回执，以及窄接口 Android AppFunctions ADB 适配器。
- `reference-app/`：受控的 Android 17 备忘录 Provider，暴露 `putMemo`、`getMemoState`、`getStoreStats` 三个 AppFunctions。
- `docs/`：架构、Android 调研、路线图与国际化指南。
- 68 项单元测试：覆盖策略、schema、重放拦截、Unicode 传输、多语种备忘录输入和 Android 命令构造。

APK、模拟器、SDK、原始设备日志、截图、回执和 SQLite 账本不会提交到 Git。

## 全语种怎么落地

Jidan 把“人类语言”与“机器协议”分开：

- 备忘录正文可以无损保存任意 Unicode 文字。
- `memo: <正文>` 是语言无关入口，正文使用任何文字系统都可以。
- 现有中文规则解析器只是一个可替换的离线适配器。
- intent ID、能力 ID、schema 字段、状态值、授权和回执始终保持稳定，不随界面语言翻译。
- Android Reference App 跟随系统语言，支持 RTL，并首批提供 23 个 locale 的种子翻译；其他语言安全回退到英文。
- 任何 BCP 47 语言包都能继续加入，不需要修改 Runtime 协议。

首批翻译是开源起点，不冒充母语人工审校。欢迎母语使用者修正文案、语气和排版。

## 快速运行

Python 3.11 或更高版本：

```bash
cd prototype
python -m unittest discover -s tests
python appfunctions_smoke.py
```

检查全部 Android 语言包：

```bash
python prototype/tools/check_locales.py
```

使用 JDK 17+ 和 Android SDK 37 构建受控 App：

```bash
cd reference-app
./gradlew :app:assembleDebug
```

Windows 请运行 `gradlew.bat`。不要用 Windows PowerShell 5.1 的默认 native pipeline 传递自然语言；UTF-8 注意事项见[原型说明](prototype/README.md#windows-unicode-arguments)。

## 安全边界

仓库不包含 Shizuku、Root、Accessibility 自动化、任意 shell 执行或通用第三方 App 控制器。真实外部动作仍必须经过确认；Android App 只是刻意受控的测试靶场。

当前 SQLite 授权账本只能在同一数据库持续存在的前提下提供本机 at-most-once 授权，不是硬件安全边界，也不承诺崩溃后的任务 exactly-once。

## 当前状态

现在已经得到的是一个能工作的实验小闭环，而不是一套完成的操作系统：

- 能力发现和保守注册；
- 未授权预检零执行；
- 与任务图绑定的授权和持久重放拦截；
- 受控 AppFunctions 写入、精确回读和 Provider 幂等；
- UTF-8 安全的主机到设备传输；
- 可扩展到全球语言的 UI 和语义动作边界。

开发和翻译贡献方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

Apache License 2.0，详见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
