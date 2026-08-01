<p align="center">
  <img src="docs/assets/jidan-hero.png" alt="Jidan は1つの AI インテントを交換可能なデバイス Binding へ接続し、最後の操作を人に残します" width="100%" />
</p>

<h1 align="center">Jidan</h1>

<p align="center">
  <strong>アプリやデバイスを横断する、Capability-first のオープンな AI アクション・ランタイム。</strong><br />
  1つのインテント契約、交換可能なプラットフォーム Binding、現実世界へ確定する最後の操作は人が行います。
</p>

<p align="center">
  <a href="#-クイックスタート"><img src="https://img.shields.io/badge/クイックスタート-195A41?style=for-the-badge" alt="クイックスタート" /></a>
  <a href="profiles/message.compose.tool.json"><img src="https://img.shields.io/badge/JCL_Profile-0.1-2F8F68?style=for-the-badge" alt="JCL Profile 0.1" /></a>
  <a href="docs/i18n/README.md"><img src="https://img.shields.io/badge/UI_Locale-23-D9A441?style=for-the-badge" alt="23個のシード UI ロケール" /></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/Contributions-Welcome-3978C6?style=for-the-badge" alt="コントリビューション歓迎" /></a>
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.zh-TW.md">繁體中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a>
</p>

> [!IMPORTANT]
> Jidan は実験段階のプロトタイプです。完成した Android ディストリビューション、権限昇格ツール、または重要な処理を任せられる本番用アシスタントではありません。管理下のアプリ、テスト端末、破棄可能なデータだけを使用してください。

## ✨ 位置づけ

現在のモバイルソフトウェアは、依然としてアプリごとのサイロを中心に構成されています。単純な目的でも、画面、広告、権限、互換性のないプラットフォーム API をまたぐ必要があります。Jidan が探究する、より小さなソフトウェア単位は**能力契約**です。信頼されていない AI プランナーは呼び出しを提案できますが、認可と実行を行えるのは決定論的な Host だけです。

```text
人の目的 → セマンティック・アクション → 能力契約 → ポリシーゲート
         → Host が選んだ Binding → ネイティブ handoff → 人による確定 → 検証可能な receipt
```

長期的な目標は「もう1つのスーパーアプリ」ではありません。Android、Apple、Web、HarmonyOS、Windows、そして将来の Host が、同じ安定したインテント意味論を実装できる薄く開かれた互換レイヤーです。

## 🔌 `message.compose`：1つの契約、複数の Binding

[`message.compose`](profiles/message.compose.tool.json) は最初の Jidan Capability Layer（JCL）Profile です。JCL は MCP Tool の能力 Profile であり、新しいプログラミング言語や転送プロトコルではありません。

```python
from jidan.message_compose import planned_message_compose_binding
from jidan.registry import CapabilityRegistry

registry = CapabilityRegistry()
planned_message_compose_binding("ios").register(registry)  # Host 側の設定

# 呼び出し側が知るのは能力だけで、プラットフォームではありません。
result = registry.invoke("message.compose", {"content": "3時に会いましょう。"})
```

| 安定した契約 | 交換可能な Binding | 現在の実証範囲 |
|---|---|---|
| `message.compose` | Android Intent | データのみのプラン。検証済み WeChat handoff も利用可能 |
| `message.compose` | Apple Shortcut / Share Sheet | データのみのプラン |
| `message.compose` | Web 編集可能ドラフト | データのみのプラン |
| `message.compose` | コミュニティ Adapter | ローカル登録。中央の公開ホワイトリストは不要 |

結果は現実の状態を明示します。

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

`handoff_planned` は呼び出しプランが準備できたことだけを表し、UI が開いたとは主張しません。実際に Android Picker が前面に表示されたことを検証した場合に限り `handoff_opened` を返します。それでも Jidan は宛先を選ばず、送信ボタンも押さないため、`sent` は `false` のままです。

## 🧭 アーキテクチャと現在の実装

```text
AI プランナー（信頼しない）
  ↓ 提案
安定した能力：message.compose
  ↓ schema · scope · grant · confirmation
決定論的なセキュリティゲート
  ↓ Host がローカルで Binding を選択し信頼
Android / Apple / Web / 新しいプラットフォーム
  ↓ ネイティブの確認画面
人が最後の操作を行う → receipt
```

現在のプロトタイプには、外部依存のない能力 Registry と Schema 検証、タスクグラフ、権限を絞った Grant、確認ゲート、SQLite によるリプレイ拒否、ハッシュチェーン化された Receipt、Android 17 AppFunctions の管理下テスト、セマンティック・サーフェス探索、さらに宛先選択も送信もしない検証済み WeChat handoff が含まれます。Android、iOS、Web 向けの `message.compose` データプランはありますが、本番品質のモバイル Agent OS が完成したという意味ではありません。

## 🛡️ セキュリティ境界

- **AI プランナーをセキュリティ境界にしません。** モデル出力は信頼されていないデータとして検証されます。
- **公開の自由は盲目的な実行を意味しません。** 誰でも Adapter を実装できますが、各端末がインストールの信頼、ポリシー、隔離、取り消しを管理します。
- **宛先ヒントは権限ではありません。** `message.compose.recipient` はプラットフォーム Binding に渡されません。
- **Adapter は成功を自己申告できません。** 配送状態は Host が生成し、第三者の出力をそのまま採用しません。
- **不明な結果は不明のまま扱います。** 外部効果が曖昧な操作を「成功」として自動再試行しません。
- **最後の決定権は利用者にあります。** 送信、支払い、削除、セキュリティ設定の変更には明示的な確定境界が必要です。

実機を接続する前に [SECURITY.md](SECURITY.md) をお読みください。

## 🚀 クイックスタート

Python 3.11+ で、外部依存のないテストスイートとクロスプラットフォーム・デモを実行します。

```bash
cd prototype
python -m unittest discover -s tests -p "test_*.py"
python message_compose_demo.py
python appfunctions_smoke.py
```

Android の全言語リソースを検証します。

```bash
python prototype/tools/check_locales.py
```

JDK 17+ と Android SDK 37 で管理下の Reference App をビルドします。

```bash
cd reference-app
./gradlew :app:assembleDebug
```

Windows では `gradlew.bat` を使用してください。PowerShell 5.1 の Unicode に関する注意点は[プロトタイプガイド](prototype/README.md#windows-unicode-arguments)にあります。

## 🌍 23個のシード Locale

Jidan は人間の言語を機械プロトコルから分離します。任意の Unicode 本文は JSON、タスクグラフ、ADB、保存、読み戻し、UI を通過できます。一方、能力 ID、Schema フィールド、Grant、ハッシュ、Receipt の値は安定した ASCII 契約のままです。Android Reference UI には、RTL のアラビア語を含む **23個のシード Locale** があります。`memo: <本文>` は言語に依存しない決定論的な入口です。

これらのシード翻訳は、コミュニティが改善するための出発点です。本ページおよび一部の言語リソースは機械支援で翻訳されており、**母語話者による全面的なレビュー済みとは主張しません**。詳細と修正方法は[言語と国際化のガイド](docs/i18n/README.md)をご覧ください。

## 🤝 コントリビューション

新しい `message.compose` プラットフォーム Binding、偽の成功を検出する適合性テスト、23個の Locale の母語レビュー、既存のセマンティック ID だけを出力する制約付き言語 Adapter、管理下のアプリや端末で再現できるテストを歓迎します。

[CONTRIBUTING.md](CONTRIBUTING.md) と [90日ロードマップ](docs/04-90-day-execution-roadmap-zh.md)から始めてください。

## ライセンス

Apache License 2.0。[LICENSE](LICENSE) と [NOTICE](NOTICE) を参照してください。
