import os
import redis
from celery import Celery, Task
import yt_dlp

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery('tasks', broker=REDIS_URL, backend=REDIS_URL)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ★★★★★ ここから修正 ★★★★★
@celery_app.task(bind=True)
def download_video(self: Task, url: str) -> dict:
    """
    指定されたURLから動画をダウンロードするCeleryタスク。
    """
    task_id = self.request.id
    
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, f'{task_id}.%(ext)s'),
        'format': 'bestvideo[vcodec*=avc1]+bestaudio[acodec*=mp4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info_dict)
            original_filename = f"{info_dict.get('title', task_id)}.{info_dict.get('ext', 'mp4')}"

            result_data = {
                'status': 'COMPLETED',
                'filepath': filepath,
                'original_filename': original_filename
            }
            return result_data
            
    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise e
# ★★★★★ ここまで修正 ★★★★★
