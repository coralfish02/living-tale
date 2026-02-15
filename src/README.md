# Project "Echo" - 自律対話型ドラマ生成システム

![Project Echo](https://img.shields.io/badge/Project-Echo-purple)
![Google Cloud](https://img.shields.io/badge/Google%20Cloud-Vertex%20AI-blue)
![Status](https://img.shields.io/badge/Status-Completed-success)

## 🎭 コンセプト

**「書かずに、育てる物語」**

従来の物語創作では、作家が全てのシーンを執筆します。しかし、Project "Echo" では：

- **作家がやること**: テーマを1行入力するだけ
- **AIがやること**: キャラクター生成、会話生成、ストーリー構築

各キャラクターは「表の性格」と「裏の目的」を持ち、自律的に会話します。
予定調和ではなく、**創発的にドラマが生まれる**システムです。

## 🌐 デモ

**公開URL**: [https://project-echo-192671776924.us-central1.run.app](https://project-echo-192671776924.us-central1.run.app)

テーマを入力するだけで、AIが自動でストーリーを生成します。

## ✨ 主な特徴

### 1. Dual-Layer（表と裏）システム

各キャラクターは二重構造を持ちます：

- **🗣️ 表の発言**: 他のキャラクターに見える会話
- **💭 裏の思考**: 読者にだけ見える本音・目的
```
例:
タクミ: 「予算の件、調べさせてもらうよ」
💭 （誰が使い込んだのか、必ず見つける）
```

### 2. 創発的ストーリー生成

**従来の方法**:
```
プロット作成 → シーン執筆 → 完成
（予定調和）
```

**Project Echo**:
```
キャラクター設定 → 自律会話 → 予測不能な展開
（創発的）
```

### 3. 起承転結の自動分類

会話終了後、AIが起承転結に自動分類：

- **起**: 状況設定
- **承**: 対立・緊張
- **転**: 秘密の暴露
- **結**: 決着・余韻

## 🏗️ 技術スタック

### Google Cloud Platform

- **Vertex AI Gemini 2.0 Flash**: 対話生成
- **Cloud Run**: サーバーレス実行環境
- **Container Registry**: Dockerイメージ管理

### フレームワーク

- **Flask**: Webサーバー
- **Docker**: コンテナ化
- **Python 3.11**: メイン言語

## 🚀 使い方

### ローカル実行
```bash
# リポジトリをクローン
git clone https://github.com/mukai-boop/project-echo.git
cd project-echo

# 仮想環境を作成
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存関係をインストール
pip install -r requirements.txt

# Google Cloud 認証
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID

# サーバー起動
python web_echo_fixed.py

# ブラウザで開く
# http://localhost:5000
```

### Google Cloud Run デプロイ
```bash
# ビルド
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/project-echo

# デプロイ
gcloud run deploy project-echo \
  --image gcr.io/YOUR_PROJECT_ID/project-echo \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 3600
```

## 📊 実行例

### 入力
```
テーマ: 学園祭の予算が5万円消えた。生徒会メンバーの誰かが使い込んだ疑惑。
```

### 出力（抜粋）

**キャラクター**:
- タクミ（17歳）
  - 表: 真面目な生徒会長
  - 裏: 犯人を見つけて責任を果たす

- アヤ（17歳）
  - 表: 几帳面な会計担当
  - 裏: 実は自分が使い込んだ。バレないようにする

**ストーリー（起）**:
```
タクミ: 「アヤさん、この5万円の記録がないんだけど...」
💭 （まさか彼女が？いや、信じたい）

アヤ: 「え、そうなの？もう一度確認させてください」
💭 （やばい、気づかれた。どうしよう...）
```

## 🎯 ターゲット

### To C（一般ユーザー）
- 自分だけの物語を楽しみたい人
- 推しキャラのドラマを見たい人
- 社会実験的なコンテンツが好きな人

### To B（クリエイター）
- 発想を超えたプロット生成ツール
- リアルな人間反応のシミュレーション
- 脚本家・小説家の補助ツール

## 🔮 今後の展開

1. **3人以上のマルチエージェント対応**
2. **Imagen 3連携**（シーン挿絵の自動生成）
3. **音声合成**（キャラクターボイス）
4. **ユーザー介入機能**（途中でヒントを与える）
5. **Trickster Engine**（予定調和を崩すランダムイベント）

## 📁 ファイル構成
```
project-echo/
├── README.md                  # このファイル
├── web_echo_fixed.py          # メインアプリケーション
├── templates/
│   └── index.html             # Webインターフェース
├── requirements.txt           # 依存ライブラリ
├── Dockerfile                 # Docker設定
├── .dockerignore              # Docker除外ファイル
└── .gitignore                 # Git除外ファイル
```

## 🏆 ハッカソン

このプロジェクトは **第4回 Agentic AI Hackathon with Google Cloud** の一環として開発されました。

### 審査基準への対応

**課題の新規性**: マルチエージェント×Dual-Layerによる創発的ドラマ生成は前例なし

**解決策の有効性**: 10-20分でストーリー生成、コスト$0.05-0.10/回

**実装品質と拡張性**: 堅牢なエラーハンドリング、自動スケーリング、明確な拡張計画

## 📄 ライセンス

MIT License

## 👤 作者

- **GitHub**: [@mukai-boop](https://github.com/mukai-boop)
- **プロジェクト**: [Project Echo](https://github.com/mukai-boop/project-echo)

## 🙏 謝辞

- Google Cloud Japan
- Vertex AI チーム
- Hackathon メンター・参加者の皆様

---

**Project "Echo" - 書かずに、育てる物語**
