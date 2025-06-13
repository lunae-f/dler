# ステージ1: ビルド環境
FROM python:3.13-slim as builder

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
# requirements.txtを作成する代わりに直接インストール
# FastAPIアプリケーションのコードより先にライブラリをインストールすることで、
# アプリケーションコードの変更時にDockerのレイヤーキャッシュが効くようにする
RUN pip install --no-cache-dir --prefix="/install" \
    "fastapi[all]" \
    "uvicorn" \
    "yt-dlp"


# ステージ2: 本番環境
FROM python:3.13-slim

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
# 【重要】ワーカー数を1に設定。複数のワーカープロセスは、それぞれが独立したメモリ空間を持つため、
# 現在のインメモリの`tasks`辞書では状態を共有できません。
# これにより"Task not found"エラーが発生します。
# 複数リクエストの並行処理には、Redisなどの外部データストアが必要です。
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
