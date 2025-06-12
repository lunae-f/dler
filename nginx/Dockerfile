# ベースイメージ
FROM nginx:alpine

# デフォルトの設定ファイルを削除
RUN rm /etc/nginx/conf.d/default.conf

# カスタム設定ファイルをコピー
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf