import os
import json
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from celery.result import AsyncResult
import redis # ★ redisライブラリをインポート

# worker.py からCeleryアプリケーションとタスクをインポート
from worker import celery_app, download_video

# --- 初期化 ---
app = FastAPI(
    title="DLer API",
    description="yt-dlpで動画をダウンロードするAPI",
    version="1.1.0"
)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ★★★★★ ここから追加 ★★★★★
# Redisクライアントの初期化
# Docker環境の環境変数を読み込む
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
# ★★★★★ ここまで追加 ★★★★★


# --- Pydanticモデル ---
class TaskRequest(BaseModel):
    url: HttpUrl


# --- APIエンドポイント ---
@app.get("/", response_class=HTMLResponse, summary="フロントエンドページを表示")
async def read_root():
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

# ★★★★★ ここから追加 ★★★★★
@app.get("/tasks/history", summary="過去10件のタスク履歴を取得")
async def get_tasks_history():
    """
    Redisに保存されているタスク履歴から最新10件を取得します。
    """
    # Redisのリストから最新10件のタスク情報(JSON文字列)を取得
    tasks_json = redis_client.lrange("task_history", 0, 9)
    tasks = [json.loads(task_str) for task_str in tasks_json]
    
    # 各タスクの最新の状態をCeleryから取得して追加
    detailed_tasks = []
    for task_info in tasks:
        task_id = task_info.get("task_id")
        task_result = AsyncResult(task_id, app=celery_app)
        
        # get_task_status と同様のロジックで詳細情報を構築
        full_details = {
            "task_id": task_id,
            "url": task_info.get("url"), # 保存しておいたURL
            "status": task_result.status,
        }
        if task_result.successful():
            full_details['details'] = task_result.result
            full_details['download_url'] = f"/files/{task_id}"
        elif task_result.failed():
            full_details['details'] = str(task_result.info)
        
        detailed_tasks.append(full_details)

    return JSONResponse(content=detailed_tasks)
# ★★★★★ ここまで追加 ★★★★★


# ★★★★★ ここから修正 ★★★★★
@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED, summary="動画ダウンロードタスクを作成")
async def create_download_task(request: TaskRequest):
    """
    タスクを作成し、その情報をRedisの履歴リストにも保存します。
    """
    task = download_video.delay(str(request.url))
    
    # Redisに保存するタスク情報を作成
    task_info = {
        "task_id": task.id,
        "url": str(request.url)
    }
    # JSON文字列としてRedisリストの先頭に追加
    redis_client.lpush("task_history", json.dumps(task_info))
    # リストが長くなりすぎないように、100件までに制限
    redis_client.ltrim("task_history", 0, 99)

    return {"task_id": task.id, "url": str(request.url)}
# ★★★★★ ここまで修正 ★★★★★


@app.get("/tasks/{task_id}", summary="タスクの状態を取得")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    
    status = task_result.status
    result = task_result.result if task_result.ready() else None
    
    response_data = {
        "task_id": task_id,
        "status": status,
    }

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
