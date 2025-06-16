# ベースとなるPythonイメージを指定
FROM python:3.10-slim

# コンテナ内での作業ディレクトリを設定
WORKDIR /app

# まず requirements.txt だけをコピーしてライブラリをインストール
# （このファイルに変更がない限り、キャッシュが使われ高速化される）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# プロジェクトの全てのファイルをコンテナにコピー
COPY . .

# FFmpegをインストール (yt-dlpが動画を処理するために推奨)
RUN apt-get update && apt-get install -y ffmpeg

# コンテナの起動時に実行されるコマンドはdocker-compose.ymlで指定
