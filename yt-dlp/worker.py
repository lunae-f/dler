import os
from celery import Celery, Task
import yt_dlp

# Docker Composeから渡される環境変数を読み込む
# 環境変数がなければ、ローカル開発用に'redis://localhost:6379/0'を使う
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Celeryインスタンスの作成時に、環境変数から取得したURLを使用
celery_app = Celery(
    'tasks',
    broker=REDIS_URL,
    backend=REDIS_URL
)

# ダウンロードディレクトリの準備
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


@celery_app.task(bind=True)
def download_video(self: Task, url: str) -> dict:
    """
    指定されたURLから動画をダウンロードするCeleryタスク。
    """
    task_id = self.request.id
    
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, f'{task_id}.%(ext)s'),
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info_dict)
            original_filename = f"{info_dict.get('title', task_id)}.{info_dict.get('ext', 'mp4')}"

            return {
                'status': 'COMPLETED',
                'filepath': filepath,
                'original_filename': original_filename
            }
            
    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise e
