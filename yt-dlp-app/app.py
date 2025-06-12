# yt-dlp-app/app.py

import os
from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL

app = Flask(__name__)

DOWNLOAD_DIR = '/app/downloads'

@app.route('/api/download', methods=['POST']) # パスを/api/..に変更
def download_video():
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        ydl_opts = {
            # 保存先のテンプレート。ファイル名はyt-dlpに任せる
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # ダウンロードされたファイルのフルパスを取得
            filename = ydl.prepare_filename(info)
            
            # フルパスからファイル名だけを抽出
            base_filename = os.path.basename(filename)
            
            # フロントエンドがアクセスするためのURLパスを生成して返す
            download_url = f"/downloads/{base_filename}"
            
            return jsonify({
                'message': 'Download complete!', 
                'download_url': download_url,
                'title': info.get('title', 'N/A')
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Flaskのデフォルトポート5000で実行
    app.run(host='0.0.0.0')