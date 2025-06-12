import os
import uuid
import threading
from flask import Flask, request, jsonify, send_from_directory
from yt_dlp import YoutubeDL, DownloadError

app = Flask(__name__)

DOWNLOAD_DIR = '/home/ubuntu/downloads'
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# ダウンロード状況を保存する辞書
# {job_id: {status: "pending"|"processing"|"completed"|"failed", progress: "...", download_url: "...", error: "..."}}
DOWNLOAD_STATUS = {}

def download_task(job_id, url):
    DOWNLOAD_STATUS[job_id] = {"status": "processing", "progress": "開始..."}
    try:
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
            'format': 'bestvideo*+bestaudio/best',
            'noplaylist': True,
            'progress_hooks': [lambda d: update_progress(job_id, d)],
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            is_playlist = False
            if 'entries' in info:
                is_playlist = True
                info = info['entries'][0]
            
            filename = ydl.prepare_filename(info)
            base_filename = os.path.basename(filename)
            download_url = f"/downloads/{base_filename}"
            
            DOWNLOAD_STATUS[job_id].update({
                "status": "completed",
                "progress": "完了",
                "download_url": download_url,
                "title": info.get('title', 'N/A'),
                "is_playlist": is_playlist
            })

    except DownloadError as e:
        error_message = str(e)
        if "Private video" in error_message:
            user_message = "この動画は非公開です。"
        elif "Age-restricted" in error_message:
            user_message = "この動画は年齢制限があります。"
        elif "No such video" in error_message:
            user_message = "指定されたURLの動画は見つかりませんでした。"
        else:
            user_message = "動画のダウンロード中にエラーが発生しました。詳細: " + error_message
        DOWNLOAD_STATUS[job_id].update({"status": "failed", "error": user_message})
    except Exception as e:
        import traceback
        traceback.print_exc()
        DOWNLOAD_STATUS[job_id].update({"status": "failed", "error": "予期せぬエラーが発生しました。詳細: " + str(e)})

def update_progress(job_id, d):
    if d['status'] == 'downloading':
        p = d.get('_percent_str', d.get('total_bytes_str', ''))
        DOWNLOAD_STATUS[job_id]['progress'] = f"ダウンロード中: {p}"
    elif d['status'] == 'finished':
        DOWNLOAD_STATUS[job_id]['progress'] = "変換中..."

@app.route('/api/download', methods=['POST'])
def download_video_async():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URLが指定されていません。'}), 400

    job_id = str(uuid.uuid4())
    DOWNLOAD_STATUS[job_id] = {"status": "pending", "progress": "キューに追加されました。"}
    
    thread = threading.Thread(target=download_task, args=(job_id, url))
    thread.start()
    
    return jsonify({"job_id": job_id}), 202 # Accepted

@app.route('/api/status/<job_id>', methods=['GET'])
def get_status(job_id):
    status = DOWNLOAD_STATUS.get(job_id)
    if status:
        return jsonify(status), 200
    return jsonify({"error": "Job ID not found"}), 404

@app.route('/downloads/<filename>')
def serve_download(filename):
    return send_from_directory(DOWNLOAD_DIR, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)


