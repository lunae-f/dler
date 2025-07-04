# DLer
[![CI](https://github.com/lunae-f/dler/actions/workflows/ci.yml/badge.svg)](https://github.com/lunae-f/dler/actions/workflows/ci.yml)

DLerは、yt-dlpを使用したWeb UIをそなえた動画ダウンローダーです。

## Run
```
git clone https://github.com/lunae-f/dler.git && cd dler
docker compose up -d --build
```

## 主な機能
- シンプルなWeb UI: 動画のURLを貼り付けるだけでダウンロードを開始できます。
- APIの提供: FastAPIによってAPIとドキュメントが提供されます。
- ステータス表示: タスクの「処理中」「成功」「失敗」といった状態をUIで確認できます。
- Dockerによる簡単な環境構築: 依存関係のインストールや環境設定の手間なく、クリーンな状態でアプリケーションを起動できます。

## 技術スタック
- バックエンド: FastAPI
- バックグラウンドタスクキュー: Celery
- メッセージブローカー / データベース: Redis
- 動画ダウンローダー: yt-dlp
- フロントエンド: HTML, CSS, JavaScript (Vanilla)
- コンテナ化: Docker

## 実行方法

### 前提条件
Dockerがインストールされていること

### 手順
1. このリポジトリをクローンします。
```
git clone https://github.com/lunae-f/dler.git
cd dler
```

2. コンテナをビルドして、バックグラウンドで起動します。
```
docker compose up -d --build
```

3. ブラウザで http://localhost:8000 にアクセスします。

4. アプリケーションを停止する場合は、以下のコマンドを実行します。（ダウンロードしたファイルも消えます！）
```
docker compose down --volumes
```

## おまけ

DLerを呼び出すDIscord Bot作りました -> [dler-discord](https://github.com/lunae-f/dler-discord)

## ライセンス
このプロジェクトは [MIT License](/LICENSE) の下で公開されています。<br>
This project is released under the MIT License.