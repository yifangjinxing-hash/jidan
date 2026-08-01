<p align="center">
  <img src="docs/assets/jidan-hero.png" alt="Jidan 將一個 AI 意圖連接到可替換的多端 Binding，並把最後動作交還給人" width="100%" />
</p>

<h1 align="center">Jidan</h1>

<p align="center">
  <strong>跨 App 與裝置、以能力為核心的開放式 AI 動作執行環境。</strong><br />
  一份意圖契約，多種平台 Binding；現實動作的最後一步仍由人決定。
</p>

<p align="center">
  <a href="#-快速開始"><img src="https://img.shields.io/badge/快速開始-195A41?style=for-the-badge" alt="快速開始" /></a>
  <a href="profiles/message.compose.tool.json"><img src="https://img.shields.io/badge/JCL_Profile-0.1-2F8F68?style=for-the-badge" alt="JCL Profile 0.1" /></a>
  <a href="docs/i18n/README.md"><img src="https://img.shields.io/badge/UI_Locale-23-D9A441?style=for-the-badge" alt="23 個種子 UI Locale" /></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/歡迎-共同建設-3978C6?style=for-the-badge" alt="歡迎共同建設" /></a>
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.zh-TW.md">繁體中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a>
</p>

> [!IMPORTANT]
> Jidan 目前仍是實驗原型，不是完整的 Android 發行版、提權工具，也不是可託付重要事務的正式產品。請只使用受控 App、測試裝置與可捨棄資料。

## ✨ 定位

今日的行動軟體仍以 App 孤島為中心。一個簡單目標，往往要穿過頁面、廣告、權限，以及彼此不相容的平台 API。Jidan 探索更小的軟體單位：一份**能力契約**。不受信任的 AI 規劃器可以提出呼叫建議，但只有確定性的 Host 能授權並執行。

```text
人的目標 → 語意動作 → 能力契約 → 策略閘門
         → Host 選擇的 Binding → 原生交接 → 人類提交 → 可驗證回執
```

長期目標不是再做一個「超級 App」，而是形成薄而開放的相容層，讓 Android、Apple、Web、HarmonyOS、Windows 與未來平台實作相同且穩定的意圖語意。

## 🔌 `message.compose`：一份契約，多端實作

[`message.compose`](profiles/message.compose.tool.json) 是第一份 Jidan Capability Layer（JCL）Profile。JCL 是 MCP Tool 的能力剖面，不是新的程式語言或傳輸協定。

```python
from jidan.message_compose import planned_message_compose_binding
from jidan.registry import CapabilityRegistry

registry = CapabilityRegistry()
planned_message_compose_binding("ios").register(registry)  # 由 Host 設定平台

# 上層只認識能力，不需要知道平台。
result = registry.invoke("message.compose", {"content": "下午三點見。"})
```

| 穩定契約 | 可替換 Binding | 目前證據 |
|---|---|---|
| `message.compose` | Android Intent | 資料計畫；另有經驗證的微信原生交接 |
| `message.compose` | Apple Shortcut / Share Sheet | 資料計畫 |
| `message.compose` | Web 可編輯草稿 | 資料計畫 |
| `message.compose` | 社群 Adapter | 本機註冊，不需要中央發布白名單 |

結果必須如實反映現實狀態：

```json
{
  "state": "handoff_planned",
  "delivery": {
    "attempted": false,
    "sent": false,
    "verified": false
  },
  "nextAction": "user_review_and_send"
}
```

`handoff_planned` 只表示呼叫計畫已準備，絕不冒充「介面已開啟」。只有真正驗證 Android Picker 已出現在前景後，才能回報 `handoff_opened`；即使如此，`sent` 仍為 `false`，因為 Jidan 不選擇收件人，也不按下傳送。

## 🧭 架構與目前進度

```text
AI 規劃器（不受信任）
  ↓ 提議
穩定能力：message.compose
  ↓ schema · scope · grant · 確認
確定性安全閘門
  ↓ Host 在本機選擇並信任 Binding
Android / Apple / Web / 新平台
  ↓ 原生審閱介面
人類完成最後動作 → 回執
```

目前原型已包含：無第三方依賴的能力註冊與 Schema 驗證、任務圖與限權 Grant、確認閘門、SQLite 重放阻擋、雜湊鏈回執、Android 17 AppFunctions 受控驗證、語意表面探索，以及不選人、不傳送的微信原生交接。Android、iOS 與 Web 的 `message.compose` 資料計畫已提供；這不代表生產級行動 Agent OS 已完成。

## 🛡️ 安全邊界

- **AI 規劃器不是安全邊界：**模型輸出一律視為不可信資料並接受驗證。
- **開放發布不等於盲目執行：**任何人都能實作 Adapter，但每台裝置仍掌握安裝信任、政策、隔離與撤銷。
- **收件人提示不是授權：**`message.compose.recipient` 不會傳入平台 Binding。
- **Adapter 不能自行宣告成功：**傳送狀態由 Host 產生，不照抄第三方輸出。
- **不確定結果仍是不確定：**有外部效果的模糊結果不會被自動重試成「成功」。
- **使用者保有最後決定權：**傳送、付款、刪除與安全設定變更必須有清楚的提交邊界。

連接真實裝置前，請先閱讀 [SECURITY.md](SECURITY.md)。

## 🚀 快速開始

使用 Python 3.11+ 執行完整的無依賴測試與跨端示範：

```bash
cd prototype
python -m unittest discover -s tests -p "test_*.py"
python message_compose_demo.py
python appfunctions_smoke.py
```

檢查全部 Android 語言資源：

```bash
python prototype/tools/check_locales.py
```

使用 JDK 17+ 與 Android SDK 37 建置受控 Reference App：

```bash
cd reference-app
./gradlew :app:assembleDebug
```

Windows 請使用 `gradlew.bat`。PowerShell 5.1 的 Unicode 注意事項請參閱[原型說明](prototype/README.md#windows-unicode-arguments)。

## 🌍 23 個種子 Locale

Jidan 將人類語言與機器協定分離。任意 Unicode 正文可穿過 JSON、任務圖、ADB、儲存、回讀與 UI；能力 ID、Schema 欄位、Grant、雜湊及回執值則維持穩定的 ASCII 契約。Android Reference UI 目前提供 **23 個種子 Locale**，包括 RTL 阿拉伯文；`memo: <正文>` 是語言無關的確定性入口。

這些種子翻譯是供社群改進的起點。本頁與部分語言資源使用機器輔助翻譯，**不宣稱已由母語者完整審校**。詳情與校訂方式請見[語言與國際化指南](docs/i18n/README.md)。

## 🤝 共同建設

歡迎貢獻新的 `message.compose` 平台 Binding、能攔截「假成功」的一致性測試、23 個 Locale 的母語校訂、只產生既有語意 ID 的受限語言 Adapter，以及可在受控 App 或裝置上重現的測試。

請先閱讀 [CONTRIBUTING.md](CONTRIBUTING.md) 與 [90 天路線圖](docs/04-90-day-execution-roadmap-zh.md)。

## 授權條款

Apache License 2.0。詳見 [LICENSE](LICENSE) 與 [NOTICE](NOTICE)。
