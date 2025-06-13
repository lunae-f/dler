# ステージ1: ビルド環境
FROM python:3.12-slim as builder

# OSパッケージの更新とビルドに必要なツールのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

# FFmpegの静的ビルドをダウンロード・インストール
# yt-dlpがフォーマット変換に利用する
# 参考: https://johnvansickle.com/ffmpeg/
# アーキテクチャに合わせてURLを変更する必要がある場合がある
# ここではamd64を想定
RUN curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz | tar -xJ --strip-components=1 -C /usr/local/bin/

# Pythonの依存関係をインストールするための準備
WORKDIR /install
COPY ./app/ /install/app/
# requirements.txtを作成する代わりに直接インストール
RUN pip install --no-cache-dir --prefix="/install" \
    "fastapi[all]" \
    "uvicorn" \
    "yt-dlp"


# ステージ2: 本番環境
FROM python:3.12-slim

# タイムゾーンをJSTに設定
ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 必要なOSパッケージをインストール (FFmpegが依存)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# ビルドステージからPythonライブラリとFFmpegをコピー
COPY --from=builder /install /usr/local
COPY --from=builder /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=builder /usr/local/bin/ffprobe /usr/local/bin/ffprobe

# アプリケーションコードをコピー
WORKDIR /app
COPY ./app/ .

# サーバーを起動
# 複数のリクエストを捌くため、ワーカー数を指定することが推奨される
# (例: CPUコア数 * 2 + 1)
# ここでは開発用に1ワーカーで起動
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
