# yt-dlp-app/app.py

import os
from flask import Flask, request, jsonify
from yt_dlp import YoutubeDL

app = Flask(__name__)

DOWNLOAD_DIR = '/app/downloads'
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

@app.route('/api/download', methods=['POST'])
def download_video():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        # yt-dlpのオプション（最高品質設定）
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'format': 'bestvideo*+bestaudio/best',
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            # ダウンロードと情報取得を同時に行う
            info = ydl.extract_info(url, download=True)
            
            # プレイリストの場合は最初の動画情報を利用する
            if 'entries' in info:
                info = info['entries'][0]
            
            # ダウンロードされたファイル名を特定
            filename = ydl.prepare_filename(info)
            base_filename = os.path.basename(filename)
            download_url = f"/downloads/{base_filename}"
            
            return jsonify({
                'message': 'Download complete!',
                'download_url': download_url,
                'title': info.get('title', 'N/A'),
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)