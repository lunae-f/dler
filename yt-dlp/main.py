"""yt-dlp動画ダウンローダーのFastAPIアプリケーション。

このアプリケーションは、動画のダウンロードタスクを作成・管理するためのWeb APIを
提供します。フロントエンドからのリクエストを受け付け、Celeryワーカーに
ダウンロード処理を依頼し、タスクの状態や結果を返すエンドポイントを定義します。

- /: フロントエンドのHTMLページを提供
- /tasks: ダウンロードタスクの作成と履歴の取得
- /files: ダウンロード済みファイルの提供
"""
import os
import json
import time
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from celery.result import AsyncResult
import redis

# --- 依存関係のインポート順を整理 ---
from logger_config import logger
from celery_instance import celery_app
from worker import download_video

# --- 初期化 ---
app = FastAPI(
    title="DLer API",
    description="yt-dlpで動画をダウンロードするAPI",
    version="1.8.0"
)
app.mount("/static", StaticFiles(directory="static"), name="static")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# --- 定数 (Redisキー & ディレクトリ設定) ---
TASK_HISTORY_ZSET_KEY = "task_history:zset"
TASK_DETAILS_HASH_KEY = "task_details:hash"
MAX_HISTORY_SIZE = 100

DOWNLOAD_DIR = "downloads"
DOWNLOAD_DIR_ABSPATH = os.path.abspath(DOWNLOAD_DIR)

class TaskRequest(BaseModel):
    url: HttpUrl

# --- ヘルパー関数 ---
def _get_task_details(task_id: str, url: str | None = None) -> dict:
    """タスクIDから詳細な情報を取得するヘルパー関数。"""
    task_result = AsyncResult(task_id, app=celery_app)
    status = task_result.status
    
    # URLが引数で渡されない場合はRedisから取得
    if url is None:
        task_info_json = redis_client.hget(TASK_DETAILS_HASH_KEY, task_id)
        if task_info_json:
            try:
                url = json.loads(task_info_json).get("url")
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Could not decode task detail for {task_id}")

    response_data = {"task_id": task_id, "status": status, "url": url}

    if task_result.ready():
        result = task_result.result
        if status == 'SUCCESS':
            response_data['details'] = result
            response_data['download_url'] = f"/files/{task_id}"
        elif status == 'FAILURE':
            # エラー情報は文字列に変換して格納
            response_data['details'] = str(result)
            
    return response_data

# --- APIエンドポイント ---
@app.get("/", response_class=HTMLResponse, summary="フロントエンドページを表示")
async def read_root():
    """フロントエンドのメインページ (index.html) を返します。"""
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.get("/tasks/history", summary=f"過去{MAX_HISTORY_SIZE}件のタスク履歴を取得")
async def get_tasks_history():
    """過去のタスク履歴を最大件数まで取得します。"""
    task_ids = redis_client.zrevrange(TASK_HISTORY_ZSET_KEY, 0, MAX_HISTORY_SIZE - 1)
    if not task_ids:
        return JSONResponse(content=[])

    tasks_details_json = redis_client.hmget(TASK_DETAILS_HASH_KEY, task_ids)
    
    detailed_tasks = []
    for task_id, task_detail_json in zip(task_ids, tasks_details_json):
        url = None
        if task_detail_json:
            try:
                url = json.loads(task_detail_json).get("url")
            except (json.JSONDecodeError, TypeError):
                pass  # このケースはヘルパー関数内で処理されるため、ここではログを残さない
        
        # ヘルパー関数を呼び出す
        detailed_tasks.append(_get_task_details(task_id, url))
        
    return JSONResponse(content=detailed_tasks)


@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED, summary="動画ダウンロードタスクを作成")
async def create_download_task(request: TaskRequest):
    """新しい動画ダウンロードタスクを作成します。"""
    original_url = str(request.url)
    task = download_video.delay(original_url)
    logger.info(f"Task {task.id} created for URL: {original_url}")
    add_task_to_history(task.id, original_url)
    return {"task_id": task.id, "url": original_url}

def add_task_to_history(task_id: str, url: str):
    """Redisにタスク情報を追加するヘルパー関数。"""
    pipe = redis_client.pipeline()
    timestamp = time.time()
    task_details = json.dumps({"url": url})
    
    pipe.zadd(TASK_HISTORY_ZSET_KEY, {task_id: timestamp})
    pipe.hset(TASK_DETAILS_HASH_KEY, task_id, task_details)
    pipe.zremrangebyrank(TASK_HISTORY_ZSET_KEY, 0, -MAX_HISTORY_SIZE - 1)
    pipe.execute()
    
    current_ids_in_zset = redis_client.zrange(TASK_HISTORY_ZSET_KEY, 0, -1)
    all_ids_in_hash = redis_client.hkeys(TASK_DETAILS_HASH_KEY)
    
    ids_to_remove_from_hash = [hash_id for hash_id in all_ids_in_hash if hash_id not in current_ids_in_zset]
    if ids_to_remove_from_hash:
        redis_client.hdel(TASK_DETAILS_HASH_KEY, *ids_to_remove_from_hash)

@app.get("/tasks/{task_id}", summary="タスクの状態を取得")
async def get_task_status(task_id: str):
    """指定されたタスクIDの状態と詳細を取得します。"""
    # ヘルパー関数を呼び出すだけで済む
    task_details = _get_task_details(task_id)
    return JSONResponse(content=task_details)


@app.get("/files/{task_id}", summary="ダウンロードしたファイルを取得")
async def download_file(task_id: str):
    """ダウンロード済みのファイルを取得します。"""
    task_result = AsyncResult(task_id, app=celery_app)
    if not task_result.successful():
        raise HTTPException(status_code=404, detail="Task not found, or has failed.")
    
    result = task_result.get()
    filepath = result.get('filepath')

    if not filepath:
        raise HTTPException(status_code=404, detail="Filepath not found in task result.")

    requested_path_abspath = os.path.abspath(filepath)
    if not requested_path_abspath.startswith(DOWNLOAD_DIR_ABSPATH):
        raise HTTPException(status_code=403, detail="Forbidden: Access to this file is not allowed.")
        
    if not os.path.exists(requested_path_abspath):
        raise HTTPException(status_code=404, detail="File not found on the server.")

    original_filename = result.get('original_filename', f'{task_id}.mp4')
    return FileResponse(path=requested_path_abspath, filename=original_filename, media_type='application/octet-stream')

@app.delete("/tasks/{task_id}", status_code=status.HTTP_200_OK, summary="タスクと関連ファイルを削除")
async def delete_task(task_id: str):
    """タスク履歴と関連するダウンロード済みファイルを削除します。"""
    task_result = AsyncResult(task_id, app=celery_app)

    if task_result.successful():
        result = task_result.result or {}
        filepath = result.get('filepath')
        if filepath and os.path.exists(filepath):
            try:
                file_to_delete_abspath = os.path.abspath(filepath)
                if file_to_delete_abspath.startswith(DOWNLOAD_DIR_ABSPATH):
                    os.remove(file_to_delete_abspath)
                    logger.info(f"Deleted file {filepath} for task {task_id}")
            except OSError as e:
                logger.error(f"Error removing file {filepath}: {e}")

    pipe = redis_client.pipeline()
    pipe.zrem(TASK_HISTORY_ZSET_KEY, task_id)
    pipe.hdel(TASK_DETAILS_HASH_KEY, task_id)
    pipe.execute()

    task_result.forget()
    logger.info(f"Deleted task {task_id} from history and Celery backend.")
    
    return {"status": "deleted", "task_id": task_id}
