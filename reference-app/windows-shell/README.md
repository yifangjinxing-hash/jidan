# JidanOS Windows Shell

JidanOS 是原生 Windows WPF 系统选择器，不使用浏览器或 WebView。它把系统视为运行时、把 `EXE / APK / IPA` 视为可检查的成品包：先选择 `Jidan / Windows / Android / iOS / Windows Phone` 系统槽，再由真实可用的后端执行，缺少能力时明确停止并报告。

> [!IMPORTANT]
> 这是兼容运行实验，不是完整 iOS、Android 或 Windows Phone 实现，也不能把商业 IPA 变成可运行程序。项目不包含 Apple、Google 或 Microsoft 的固件、私有框架、SDK 或代码。

## 当前支持矩阵

| 成品包 / 系统槽 | 当前路由 | 状态 |
|---|---|---|
| Windows EXE | Windows 原生进程 | 可运行；陌生 EXE 启动前显示路径、SHA-256 和无沙箱警告 |
| Android APK | 已连接的 ADB / Android guest | 可安装并启动；没有设备时如实报告缺少引擎 |
| iOS IPA | clean-room ARM64 HLE | 仅运行项目自生成、未加密、无 Apple 框架依赖的受控 Mach-O 样本 |
| Jidan | 统一检查与路由 | 可识别 PE、APK/ZIP、IPA/Mach-O 64 |
| Windows Phone | 后端探测槽 | UI 与契约已建立，执行引擎尚未接入 |

## 构建与运行

要求 Windows 10/11、.NET Framework 4.8 和 Node.js。Android SDK platform/build-tools 与 JDK 是构建真实样本 APK 的可选依赖；脚本会优先使用 `ANDROID_SDK_ROOT`、`ANDROID_HOME` 和 `JAVA_HOME`，缺少它们时仍会生成 clean-room 测试容器。

```bat
build.cmd
start.cmd
```

也可以直接双击 `JidanOS.exe`，把成品包拖进窗口，或按 `Ctrl+O` 导入。

## 验证

```powershell
$results = Join-Path $PWD 'test-results.txt'
$process = Start-Process .\JidanOS.exe -ArgumentList '--test', $results -Wait -PassThru
Get-Content $results
if ($process.ExitCode -ne 0) { throw "Tests failed: $($process.ExitCode)" }
```

测试覆盖 PE、APK、IPA/Mach-O 检查，Windows 子进程执行，以及受控 ARM64 guest/hostcall 路径。GitHub 上的 [Windows Shell CI](../../.github/workflows/windows-shell.yml) 会在 `windows-latest` 重新构建、运行测试并上传无 PDB 的 ZIP 成品。

## 安全边界

- 外来 EXE 是真实本机代码；只运行你信任的文件，必要时先使用 Windows Sandbox 或虚拟机。
- APK 安装到当前 ADB 设备；设备选择与数据隔离由使用者负责。
- IPA 路由在第一条未知指令、缺失框架或策略拒绝时停止，不猜测系统行为。
- 示例 APK 使用本机 Android debug keystore 签名；密钥、构建缓存、PDB 和测试日志不会进入 Git。
