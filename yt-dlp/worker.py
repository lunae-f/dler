import os
import re
import redis
from celery import Celery, Task
import yt_dlp

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery('tasks', broker=REDIS_URL, backend=REDIS_URL)

DOWNLOAD_DIR = "downloads"


def sanitize_filename(filename: str) -> str:
    """ファイル名として使えない文字をアンダースコアに置換します。"""
    return re.sub(r'[\\/*?:"<>|]', "_", filename)


@celery_app.task(bind=True, throws=(Exception,))
def download_video(self: Task, url: str) -> dict:
    """
    指定されたURLから動画をダウンロードし、サニタイズされたファイル名と共に結果を返します。
    """
    task_id = self.request.id
    
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, f'{task_id}.%(ext)s'),
        'format': 'bestvideo[vcodec*=avc1]+bestaudio[acodec*=mp4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # 動画情報を抽出してダウンロードを実行
        info_dict = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info_dict)
        
        # ファイル名をサニタイズ
        title = info_dict.get('title', task_id)
        ext = info_dict.get('ext', 'mp4')
        original_filename = f"{sanitize_filename(title)}.{ext}"

        # 結果を辞書として返す
        result_data = {
            'filepath': filepath,
            'original_filename': original_filename
        }
        return result_data
