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
  <a href="profiles/frontends/zh-Latn-pinyin.frontend.json"><img src="https://img.shields.io/badge/Pinyin_Frontend-0.1-8A5A2B?style=for-the-badge" alt="Pinyin Frontend 0.1" /></a>
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
         → Host 選擇的 Binding → 可驗證交接回執 → 人類提交
                                                    （目前不驗證最終傳送）
```

長期目標不是再做一個「超級 App」，而是形成薄而開放的相容層，讓 Android、Apple、Web、HarmonyOS、Windows 與未來平台實作相同且穩定的意圖語意。

> **統一語意，不統一實作。** 自然語言與拼音是可替換的 Frontend；JCL 是機器契約；Kotlin、Swift、JavaScript、C/C++ 只是 Host 或 Adapter 的實作選擇；Web Binding 仍受瀏覽器沙箱限制。參見[歷史鏡鑑與路線護欄](docs/06-history-lessons-and-route-guardrails-zh.md)。

## 🔌 `message.compose`：一份契約，多端實作

[`message.compose`](profiles/message.compose.tool.json) 是第一份 Jidan Capability Layer（JCL）Profile。JCL 0.1 的首個公開序列化採用與 MCP 相容的 Tool Profile；JCL 本身不是新的程式語言，也不綁定單一傳輸或工作階段模型。

```python
from jidan.models import Step, TaskPlan

# 上層只提出能力，不選擇平台，也不直接呼叫 Adapter。
plan = TaskPlan(
    id="compose-demo",
    goal="準備一份訊息草稿",
    steps=(Step(
        id="compose",
        capability="message.compose",
        arguments={"content": "下午三點見。"},
    ),),
)
# 可信 Host 繼續完成驗證、授權、確認、Binding 選擇、執行與回執。
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

## 🔤 可選拼音編譯前端

[`Pinyin Frontend 0.1`](profiles/frontends/zh-Latn-pinyin.frontend.json) 是位於 Host 輸入邊界的可選、僅編譯前端，**不是 JCL 位元組碼，也不是新 DSL**。它只把受限的拼音控制別名編譯成既有 `message.compose` 呼叫提案；能力 ID、Schema 與 JCL 0.1 保持不變，訊息正文則逐字保留，不會被靜默改寫或自動轉成漢字。

這個 Frontend 沒有授權、Grant、執行、選擇收件人或傳送的權力。無聲調拼音只在能唯一命中受審查別名時接受；未知輸入或同音歧義一律拒絕，交還使用者釐清。編譯結果仍是不受信任的提案，必須完整通過原有 Schema、策略、授權、確認、執行與回執鏈。設計與威脅邊界詳見[JCL 拼音前端說明](docs/05-jcl-pinyin-frontend-zh.md)。

## 🧭 架構與目前進度

```text
AI 規劃器（不受信任）
  ↓ 提議
穩定能力：message.compose
  ↓ schema · scope · grant · 確認
確定性安全閘門
  ↓ Host 在本機選擇並信任 Binding
Android / Apple → 行動端原生審閱介面
Web → 可編輯 Web 審閱介面
新平台 → Binding 自有審閱介面
  ├→ 可驗證交接回執（sent=false）
  └→ 人類完成最後動作（目前不在 Jidan 的傳送驗證範圍內）
```

| 新增層級 | 狀態 | 目前證據 |
|---|---:|---|
| 可選 Pinyin Frontend 0.1 | 🧪 | 受限控制別名 → `message.compose` 提案；正文原樣保留，歧義拒絕 |

目前原型已包含：無第三方依賴的能力註冊與 Schema 驗證、任務圖與限權 Grant、確認閘門、SQLite 重放阻擋、雜湊鏈回執、Android 17 AppFunctions 受控驗證、語意表面探索，以及不選人、不傳送的微信原生交接。Android、iOS 與 Web 的 `message.compose` 資料計畫已提供；這不代表生產級行動 Agent OS 已完成。

## 🛡️ 安全邊界

- **AI 規劃器不是安全邊界：**模型輸出一律視為不可信資料並接受驗證。
- **拼音前端不擁有權限：**它只能產生 `message.compose` 提案，不能授權、執行、選擇收件人或傳送；歧義必須拒絕。
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
python pinyin_frontend_demo.py
python appfunctions_smoke.py
```

兩個訊息示範預設都停在 `awaiting_confirmation`。`--simulate-approval` 只用於繼續示範本機資料計畫的後續階段，會明確標示為模擬批准，不能視為使用者真的確認。

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

Jidan 將人類語言與機器協定分離。任意 Unicode 正文可穿過 JSON、任務圖、ADB、儲存、回讀與 UI；能力 ID、Schema 欄位、Grant、雜湊及回執值則維持穩定的 ASCII 契約。Android Reference UI 目前提供 **23 個種子 Locale**，包括 RTL 阿拉伯文；`memo: <正文>` 是語言無關的確定性入口。Pinyin Frontend 只是其中一個可選輸入前端，不是所有語言必須經過的底層；它只編譯控制別名，不改寫使用者正文。

這些種子翻譯是供社群改進的起點。本頁與部分語言資源使用機器輔助翻譯，**不宣稱已由母語者完整審校**。詳情與校訂方式請見[語言與國際化指南](docs/i18n/README.md)。

## 🤝 共同建設

歡迎貢獻新的 `message.compose` 平台 Binding、能攔截「假成功」的一致性測試、23 個 Locale 的母語校訂、只產生既有語意 ID 的受限語言 Adapter，以及可在受控 App 或裝置上重現的測試。

請先閱讀 [CONTRIBUTING.md](CONTRIBUTING.md) 與 [90 天路線圖](docs/04-90-day-execution-roadmap-zh.md)。

## 授權條款

Apache License 2.0。詳見 [LICENSE](LICENSE) 與 [NOTICE](NOTICE)。
