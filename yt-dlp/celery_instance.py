# yt-dlp/celery_instance.py
import os
from celery import Celery

# RedisのURLを環境変数から取得
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Celeryアプリケーションインスタンスを作成
# これを他のモジュール（main.py, worker.py）からインポートして使用する
celery_app = Celery('tasks', broker=REDIS_URL, backend=REDIS_URL, include=['worker'])

