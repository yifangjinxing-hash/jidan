# Jidan Android「小事清单 + 手脑」实验包

这是下载解压后即可安装的 Android 调试实验包，不是正式商店版本。包内有三只 APK：Jidan Shell、本地小事清单和无网络合成实验室。

## 安装

需要 Android 8.0 或更高版本、已连接的测试手机或模拟器，以及可用的 `adb`。

在解压后的当前目录依次运行以下命令，不需要修改文件名：

```powershell
adb install -r -t .\JidanDailyDemo-0.1-debug.apk
adb install -r -t .\JidanAccessibilitySandbox-0.1-debug.apk
adb install -r -t .\JidanShell-0.4-debug.apk
```

macOS 或 Linux 终端使用：

```bash
adb install -r -t ./JidanDailyDemo-0.1-debug.apk
adb install -r -t ./JidanAccessibilitySandbox-0.1-debug.apk
adb install -r -t ./JidanShell-0.4-debug.apk
```

三只 APK 来自同一个 CI 实验包，具有互相匹配的签名身份与实验契约。不要把其他来源或其他版本的 APK 混入这组文件；身份不匹配时 Jidan 会停止执行。

## 先试玩一件真实小事

1. 打开 **Jidan Shell**。
2. 点首页的 **记小事**；它会执行“记下明天买鸡蛋”。
3. 如果 Android 打开无障碍设置，请亲自开启 **鸡蛋辅助操作**，然后返回；服务就绪时实验会自动继续，不会再弹一张同义确认卡。
4. 鸡蛋会打开**小事清单**、填写、保存并重新核验，然后尝试返回 Shell。
5. Shell 显示“已经记下”后，可从桌面单独打开**小事清单**，完成、撤销或清空已完成事项。

首页是**支付 / 手 / 记事**三个图形入口。「手」面板统一展示 Jidan 自研手与兼容手。公共 CI 不携带第三方 APK；只有本地授权构建会把原签名 companion 作为受哈希约束的内置资产打包。

## 再试玩合成实验

在 Shell 输入“开始手脑实验”。它会打开无网络实验室，完成假收款人、假金额、假密码、假验证码和假提交五步。看到“实验完成：外部交易 0 笔”即表示合成动作链完成。

如果系统或手机厂商之后停用了无障碍服务，需要重新开启。小事清单和实验室都没有 `INTERNET` 权限。清单正文只保存在小事清单本机存储中；假密码和假验证码原文不会写入 Jidan 计划、回执或实验应用存储。

`SHA256SUMS.txt` 记录了本包三只 APK 的 SHA-256，可在安装前核对文件完整性。
