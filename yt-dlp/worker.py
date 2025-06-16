import os
import json
import redis
from celery import Celery, Task
import yt_dlp

# Docker Composeから渡される環境変数を読み込む
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Celeryインスタンスの作成
celery_app = Celery(
    'tasks',
    broker=REDIS_URL,
    backend=REDIS_URL
)

# ★★★★★ ここから追加 ★★★★★
# ワーカー内でもRedisクライアントを初期化
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
# ★★★★★ ここまで追加 ★★★★★

# ダウンロードディレクトリの準備
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


@celery_app.task(bind=True)
def download_video(self: Task, url: str) -> dict:
    """
    指定されたURLから動画をダウンロードし、成功時にキャッシュを作成するCeleryタスク。
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

            # ★★★★★ ここから追加 ★★★★★
            # ダウンロード成功後、キャッシュをRedisに保存
            # Key: 動画URL, Value: 完了したタスクのID
            redis_client.hset("video_cache", url, task_id)
            # ★★★★★ ここまで追加 ★★★★★

            # Celeryに返す結果
            result_data = {
                'status': 'COMPLETED',
                'filepath': filepath,
                'original_filename': original_filename
            }
            return result_data
            
    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise e
