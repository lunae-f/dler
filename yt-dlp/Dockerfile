# ==================================
#  ステージ1: ビルダーステージ
# ==================================
# Pythonパッケージのインストールに必要なツールを含むベースイメージを使用
FROM python:3.10-slim-bookworm AS builder

# 環境変数の設定
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# ビルドに必要な依存関係とffmpegをインストール
# --no-install-recommends で不要なパッケージのインストールを防ぐ
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc build-essential && \
    rm -rf /var/lib/apt/lists/*

# アプリケーション用の仮想環境を作成
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# requirements.txtをコピーし、パッケージを仮想環境にインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==================================
#  ステージ2: 最終ステージ
# ==================================
# 実行用に、同じく軽量なslimイメージを使用
FROM python:3.10-slim-bookworm

# 作業ディレクトリを設定
WORKDIR /app

# 実行時に必要なffmpegのみをインストール
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# ビルダーステージから、インストール済みの仮想環境をコピー
COPY --from=builder /opt/venv /opt/venv

# アプリケーションコードをコピー
COPY . .

# 仮想環境を有効化
ENV PATH="/opt/venv/bin:$PATH"

# ポートを公開（ドキュメントとしての意味合い）
EXPOSE 8000

# コンテナ起動時のコマンドはdocker-compose.ymlで指定されます
