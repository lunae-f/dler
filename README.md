# DLer
[![CI/CD Pipeline](https://github.com/lunae-f/dler/actions/workflows/ci.yml/badge.svg)](https://github.com/lunae-f/dler/actions/workflows/ci.yml)

DLerは、ブラウザから動画のURLを送信することで、yt-dlp を利用してサーバーサイドで動画をダウンロードするためのWebアプリケーションです。

## 主な機能
- Web UIによる簡単な操作: 動画のURLを貼り付けるだけでダウンロードを開始できます。
- 非同期タスク処理: Celery を利用して、重いダウンロード処理をバックグラウンドで実行するため、UIがブロックされません。
- リアルタイムなステータス更新: タスクの「待機中」「処理中」「成功」「失敗」といった状態をフロントエンドでリアルタイムに確認できます。
- タスク履歴の保存: Redis を使用して、過去のタスク履歴を保存・表示します。
- Dockerによる環境構築: Docker と Docker Compose を使うことで、依存関係のインストールや環境設定の手間なく、簡単にアプリケーションを起動できます。

## 技術スタック
- バックエンド: FastAPI
- バックグラウンドタスクキュー: Celery
- メッセージブローカー / データベース: Redis
- 動画ダウンローダー: yt-dlp
- フロントエンド: HTML, CSS, JavaScript (Vanilla)
- コンテナ化: Docker, Docker Compose

## 実行方法

### 前提条件
- Docker
- Docker Compose

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
4. アプリケーションを停止する場合は、以下のコマンドを実行します。
```
docker compose down
```

## (メモ)テスト

apiコンテナで以下のコマンドを実行

```sh
playwright install
playwright install-deps
pytest
```

## ライセンス
このプロジェクトは MIT License の下で公開されています。<br>
This project was created with ❤️‍🔥 by Lunae.