<p align="center">
  <img src="docs/assets/jidan-hero.png" alt="Jidan は1つの AI インテントを交換可能なデバイス Binding へ接続し、最後の操作を人に残します" width="100%" />
</p>

<h1 align="center">Jidan</h1>

<p align="center">
  <strong>実際のマイクロアクションを優先し、1つの手間を小さく、観測可能で安全にします。</strong><br />
  ローカルで準備し、事実どおりに引き渡し、不可逆な確定は人に残します。
</p>

<p align="center">
  <a href="docs/11-daily-note-cross-app-hand-zh.md"><img src="https://img.shields.io/badge/Android_デイリー操作-0.3-7B61A8?style=for-the-badge" alt="Jidan Shell 0.3 のクロスアプリ操作" /></a>
  <a href="reference-app/ios-shell/README.md"><img src="https://img.shields.io/badge/iOS_観測可能プロトタイプ-0.1-8B7AC8?style=for-the-badge" alt="Jidan iOS Shell 0.1" /></a>
  <a href="#-開発者向けクイックスタート"><img src="https://img.shields.io/badge/開発者向けスタート-195A41?style=for-the-badge" alt="開発者向けクイックスタート" /></a>
  <a href="profiles/message.compose.tool.json"><img src="https://img.shields.io/badge/JCL_Profile-0.1-2F8F68?style=for-the-badge" alt="JCL Profile 0.1" /></a>
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
> Jidan は実験段階のプロトタイプです。Android 実験版には Shell、ローカルのタスクリスト、隔離フィクスチャの3つの APK があり、Android 17 エミュレーターで一連の操作を検証しています。ただし、ストア署名済み製品、既定ランチャー、独立 OS ではありません。管理下のアプリ、テスト端末、破棄可能なデータだけを使用してください。

<p align="center">
  <a href="reference-app/shell/README.md"><img src="docs/assets/jidan-shell-daily-0.3.png" alt="Jidan Shell 0.3 の最小 Android 操作画面" width="360" /></a>
  <a href="reference-app/ios-shell/README.md"><img src="docs/assets/jidan-ios-shell-0.1.png" alt="iPhone 16 Simulator で全画面動作する Jidan iOS Shell 0.1" width="360" /></a>
</p>

## ✨ 位置づけ

現在のモバイルソフトウェアは、依然としてアプリごとのサイロを中心に構成されています。単純な目的でも、画面、広告、権限、互換性のないプラットフォーム API をまたぐ必要があります。Jidan が探究する、より小さなソフトウェア単位は**能力契約**です。信頼されていない AI プランナーは呼び出しを提案できますが、認可と実行を行えるのは決定論的な Host だけです。

```text
人の目的 → セマンティック・アクション → 能力契約 → ポリシーゲート
         → Host が選んだ Binding → 検証可能な handoff receipt → 人による確定
                                                            （最終送信は現在の検証範囲外）
```

長期的な目標は「もう1つのスーパーアプリ」ではありません。Android、Apple、Web、HarmonyOS、Windows、そして将来の Host が、同じ安定したインテント意味論を実装できる薄く開かれた互換レイヤーです。

> **共有するのは意味論であり、実装ではありません。** 自然言語と UI 入力は JCL の機械契約の外側にあり、Kotlin、Swift、JavaScript、C/C++ は Host または Adapter の実装選択です。Web Binding は引き続きブラウザー Sandbox の制約を受けます。Pinyin 0.1 は凍結済みの実験で、プロジェクトの基盤ではありません。[歴史から得た設計上の教訓](docs/06-history-lessons-and-route-guardrails-zh.md)（中国語）も参照してください。

## 🧭 実際の小さな行動を優先

Jidan は、日常の小さな面倒を先に検証し、そこからプロトコルを逆算します。最初の金融実験は、管理下の Android/ADB Lab で Host が固定した Alipay バージョン、署名、前面コンポーネントを確認し、その信頼済み front door を開くだけです。宛先、アカウント、金額を受け取らず、非公開 Scheme を使わず、支払い完了も主張しません。これは Adapter の実証であり、一般向け製品や「AI 自動送金」ではありません。[Alipay micro-action とプロトコル上の教訓](docs/09-alipay-micro-actions-and-protocol-lessons-zh.md)（中国語）を参照してください。

## 🔌 `message.compose`：1つの契約、複数の Binding

[`message.compose`](profiles/message.compose.tool.json) は最初の Jidan Capability Layer（JCL）Profile です。JCL 0.1 の最初の公開シリアライズ形式は MCP 互換の Tool Profile を使いますが、JCL 自体は新しいプログラミング言語でも、特定の転送・セッション方式に固定されたものでもありません。

```python
from jidan.models import Step, TaskPlan

# 呼び出し側は能力を提案するだけで、Platform や Adapter を選びません。
plan = TaskPlan(
    id="compose-demo",
    goal="メッセージの下書きを準備する",
    steps=(Step(
        id="compose",
        capability="message.compose",
        arguments={"content": "3時に会いましょう。"},
    ),),
)
# 信頼された Host が検証、Grant、確認、Binding 選択、実行、Receipt を行います。
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

## 🧪 Conformance Lab：Nine Lights

Nine Lights は共有意味論を検査するための fixture としてのみ残します。Jidan のユーザー機能でも、クロスプラットフォーム App 自動化の証明でもありません。
Python Host と独立した JavaScript Host は同じ[適合性ベクトル](profiles/conformance/game.ninelights.vectors.json)を再生します。実験コードとビルド方法は[プロトタイプガイド](prototype/README.md#nine-lights-conformance-spike)に残し、範囲は[証拠ノート](docs/07-universal-game-spike-zh.md)（中国語）で限定します。

> [!NOTE]
> Pinyin Frontend 0.1 実験は 2026-08-02 に凍結されました。コード、Profile、デモ、テストは互換性と再現のために残しますが、アクティブなルートやクイックスタートではありません。新しい構文やエイリアスは受け付けません。

## 🧭 アーキテクチャと現在の実装

```text
AI プランナー（信頼しない）
  ↓ 提案
安定した能力：message.compose
  ↓ schema · scope · grant · confirmation
決定論的なセキュリティゲート
  ↓ Host がローカルで Binding を選択し信頼
Android / Apple → モバイルのネイティブ確認画面
Web → 編集可能な Web 確認画面
新しいプラットフォーム → Binding 固有の確認画面
  ├→ 検証可能な handoff receipt（sent=false）
  └→ 人が最後の操作を行う（最終送信は現在の Jidan 検証範囲外）
```

現在のプロトタイプには、外部依存のない能力 Registry と Schema 検証、タスクグラフ、権限を絞った Grant、確認ゲート、SQLite によるリプレイ拒否、ハッシュチェーン化された Receipt、Android 17 AppFunctions の管理下テスト、セマンティック・サーフェス探索、宛先選択も送信もしない WeChat handoff、そして Apple Simulator で起動する [SwiftUI iOS Shell](reference-app/ios-shell/README.md) が含まれます。iOS の Alipay 入口は公開・監査可能な契約が見つかるまで未接続です。これは本番品質のモバイル Agent OS が完成したという意味ではありません。

## 🛡️ セキュリティ境界

- **AI プランナーをセキュリティ境界にしません。** モデル出力は信頼されていないデータとして検証されます。
- **公開の自由は盲目的な実行を意味しません。** 誰でも Adapter を実装できますが、各端末がインストールの信頼、ポリシー、隔離、取り消しを管理します。
- **宛先ヒントは権限ではありません。** `message.compose.recipient` はプラットフォーム Binding に渡されません。
- **Adapter は成功を自己申告できません。** 配送状態は Host が生成し、第三者の出力をそのまま採用しません。
- **認可は名前だけに結び付きません。** Grant は有効な能力定義を固定し、Schema、effect、Adapter ID が変われば再認可を要求します。
- **入力 Frontend は権限ではありません。** 言語や UI の入力は Grant を発行せず、実行、プラットフォーム選択、確認済み payload の書き換えもできません。
- **不明な結果は不明のまま扱います。** 外部効果が曖昧な操作を「成功」として自動再試行しません。
- **最後の決定権は利用者にあります。** 送信、支払い、削除、セキュリティ設定の変更には明示的な確定境界が必要です。

実機を接続する前に [SECURITY.md](SECURITY.md) をお読みください。

## 🚀 開発者向けクイックスタート

Python 3.11+ で、外部依存のないテストスイートとクロスプラットフォーム・デモを実行します。

```bash
cd prototype
python -m unittest discover -s tests -p "test_*.py"
python message_compose_demo.py
python appfunctions_smoke.py
```

メッセージデモは既定で `awaiting_confirmation` で停止します。`--simulate-approval` は明示的なシミュレーションで、実際のユーザー確認を示しません。これは開発者向けの経路で、一般利用者向けの導入手順ではありません。Nine Lights は Conformance Lab の索引に残りますが、この経路には含めません。

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

凍結済みの Pinyin Frontend は互換性と再現のためだけに残されており、JCL の共通言語でも、すべての入力が通る基盤でもありません。

これらのシード翻訳は、コミュニティが改善するための出発点です。本ページおよび一部の言語リソースは機械支援で翻訳されており、**母語話者による全面的なレビュー済みとは主張しません**。詳細と修正方法は[言語と国際化のガイド](docs/i18n/README.md)をご覧ください。

## 🤝 コントリビューション

新しい `message.compose` プラットフォーム Binding、偽の成功を検出する適合性テスト、23個の Locale の母語レビュー、既存のセマンティック ID だけを出力する制約付き言語 Adapter、管理下のアプリや端末で再現できるテストを歓迎します。

[CONTRIBUTING.md](CONTRIBUTING.md)、[マイクロアクションと Alipay の境界](docs/09-alipay-micro-actions-and-protocol-lessons-zh.md)、[90日ロードマップ](docs/04-90-day-execution-roadmap-zh.md)、[直近7日間のプロトコルレビュー](docs/08-seven-day-protocol-review-zh.md)（簡体字中国語）から始めてください。

## ライセンス

Apache License 2.0。[LICENSE](LICENSE) と [NOTICE](NOTICE) を参照してください。
