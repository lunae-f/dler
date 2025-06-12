# ベースイメージ
FROM python:3.12-slim

# ffmpegをインストール
RUN apt-get update && apt-get install -y ffmpeg

# yt-dlp と Flask をインストール
RUN pip install --no-cache-dir yt-dlp Flask gunicorn

# 作業ディレクトリを作成・設定
WORKDIR /app

# アプリケーションコードをコピー
COPY . .

# ダウンロードした動画を保存するディレクトリを作成
RUN mkdir /app/downloads

# コンテナ起動時にAPIサーバーを実行
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]