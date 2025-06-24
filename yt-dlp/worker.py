import os
import re
from typing import TypedDict

import redis
from celery import Celery, Task
import yt_dlp

# --- 型定義 ---
class DownloadResult(TypedDict):
    """ダウンロード結果として返される辞書の型定義。"""
    filepath: str
    original_filename: str


# --- 初期化 ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery('tasks', broker=REDIS_URL, backend=REDIS_URL)
DOWNLOAD_DIR = "downloads"


def sanitize_filename(filename: str) -> str:
    """ファイル名として使えない文字をアンダースコアに置換します。"""
    return re.sub(r'[\\/*?:"<>|]', "_", filename)


@celery_app.task(bind=True, throws=(Exception,))
def download_video(self: Task, url: str) -> DownloadResult:
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
        info_dict = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info_dict)
        
        title = info_dict.get('title', task_id)
        ext = info_dict.get('ext', 'mp4')
        original_filename = f"{sanitize_filename(title)}.{ext}"

        # 型定義に沿った結果を辞書として返す
        result_data: DownloadResult = {
            'filepath': filepath,
            'original_filename': original_filename
        }
        return result_data
