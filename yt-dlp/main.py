import os
import json
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from celery.result import AsyncResult
import redis

# worker.py からCeleryアプリケーションとタスクをインポート
from worker import celery_app, download_video

# --- 初期化 ---
app = FastAPI(
    title="DLer API",
    description="yt-dlpで動画をダウンロードするAPI",
    version="1.2.0"
)
app.mount("/static", StaticFiles(directory="static"), name="static")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# --- Pydanticモデル ---
class TaskRequest(BaseModel):
    url: HttpUrl

# --- APIエンドポイント ---
@app.get("/", response_class=HTMLResponse, summary="フロントエンドページを表示")
async def read_root():
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.get("/tasks/history", summary="過去10件のタスク履歴を取得")
async def get_tasks_history():
    tasks_json = redis_client.lrange("task_history", 0, 9)
    tasks = [json.loads(task_str) for task_str in tasks_json]
    
    detailed_tasks = []
    for task_info in tasks:
        task_id = task_info.get("task_id")
        task_result = AsyncResult(task_id, app=celery_app)
        
        full_details = {
            "task_id": task_id,
            "url": task_info.get("url"),
            "status": task_result.status,
        }
        if task_result.successful():
            full_details['details'] = task_result.result
            full_details['download_url'] = f"/files/{task_id}"
        elif task_result.failed():
            full_details['details'] = str(task_result.info)
        
        detailed_tasks.append(full_details)

    return JSONResponse(content=detailed_tasks)

# ★★★★★ ここから大幅に修正 ★★★★★
@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED, summary="動画ダウンロードタスクを作成（キャッシュ確認付き）")
async def create_download_task(request: TaskRequest):
    """
    タスクを作成します。もし過去に同じURLのダウンロードが成功していれば、
    新しいタスクは作らずに過去のタスク情報を返します。
    """
    url_str = str(request.url)

    # 1. キャッシュを確認
    cached_task_id = redis_client.hget("video_cache", url_str)
    if cached_task_id:
        task_result = AsyncResult(cached_task_id, app=celery_app)
        # 2. キャッシュされたタスクが有効か検証
        if task_result.successful():
            # ファイルが物理的に存在するか確認
            filepath = task_result.result.get('filepath')
            if filepath and os.path.exists(filepath):
                # 3. 有効なキャッシュヒット！
                # ユーザーの履歴リストにこのキャッシュされたタスクを追加
                add_task_to_history(cached_task_id, url_str)
                # 過去のタスクIDを返却
                return {"task_id": cached_task_id, "url": url_str}

    # 4. キャッシュがない、または無効な場合 (キャッシュミス)
    # 新しいタスクを作成
    task = download_video.delay(url_str)
    # ユーザーの履歴リストに新しいタスクを追加
    add_task_to_history(task.id, url_str)
    
    return {"task_id": task.id, "url": url_str}

def add_task_to_history(task_id: str, url: str):
    """
    タスク情報を履歴リスト(Redis)の先頭に追加するヘルパー関数。
    """
    task_info = {"task_id": task_id, "url": url}
    # 履歴に同じタスクIDが重複しないように、一度削除してから追加
    redis_client.lrem("task_history", 0, json.dumps(task_info))
    redis_client.lpush("task_history", json.dumps(task_info))
    redis_client.ltrim("task_history", 0, 99)
# ★★★★★ ここまで大幅に修正 ★★★★★


@app.get("/tasks/{task_id}", summary="タスクの状態を取得")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    
    status = task_result.status
    result = task_result.result if task_result.ready() else None
    
    response_data = {"task_id": task_id, "status": status}

    if status == 'SUCCESS':
        response_data['details'] = result
        response_data['download_url'] = f"/files/{task_id}"
    elif status == 'FAILURE':
        response_data['details'] = str(result)
    
    return JSONResponse(content=response_data)


@app.get("/files/{task_id}", summary="ダウンロードしたファイルを取得")
async def download_file(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)

    if not task_result.successful():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Task not found, not completed, or failed."
        )

    result = task_result.get()
    filepath = result.get('filepath')
    original_filename = result.get('original_filename', f'{task_id}.mp4')

    if not filepath or not os.path.exists(filepath):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="File not found on the server. It might have been deleted."
        )

    return FileResponse(
        path=filepath,
        filename=original_filename,
        media_type='application/octet-stream'
    )
