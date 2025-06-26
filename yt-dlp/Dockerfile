# ==================================
#  ステージ1: ビルダーステージ
# ==================================
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ビルドに必要な依存関係をインストール
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc build-essential && \
    rm -rf /var/lib/apt/lists/*

# 仮想環境を作成
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# requirements.txtをコピーして依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==================================
#  ステージ2: 最終ステージ
# ==================================
FROM python:3.13-slim

# 非rootユーザーを作成し、そのユーザーのホームディレクトリを作成
RUN useradd --create-home --shell /bin/bash appuser

# 作業ディレクトリを設定
WORKDIR /app

# yt-dlpが動画の結合に使うffmpegをインストール
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# ビルダーステージから仮想環境をコピー
COPY --from=builder /opt/venv /opt/venv

# アプリケーションのソースコードをコピー (.dockerignoreで不要ファイルは除外)
COPY . .

# ダウンロードディレクトリを作成し、所有者をappuserに変更
RUN mkdir -p /app/downloads && chown -R appuser:appuser /app/downloads

# ユーザーをappuserに切り替え
USER appuser

# 仮想環境のパスを通す
ENV PATH="/opt/venv/bin:$PATH"

# コンテナがリッスンするポートを指定
EXPOSE 8000

# コンテナ起動時に実行されるデフォルトコマンド
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
