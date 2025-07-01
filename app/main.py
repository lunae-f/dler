"""yt-dlp動画ダウンローダーのFastAPIアプリケーション。

このアプリケーションは、動画のダウンロードタスクを作成・管理するためのWeb APIを
提供します。フロントエンドからのリクエストを受け付け、Celeryワーカーに
ダウンロード処理を依頼し、タスクの状態や結果を返すエンドポイントを定義します。

- /: フロントエンドのHTMLページを提供
- /tasks: ダウンロードタスクの作成と状態取得
- /files: ダウンロード済みファイルの提供・削除
"""
import os
import shutil
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from celery.result import AsyncResult
import redis

from logger_config import logger
from celery_instance import celery_app
from worker import download_video

app = FastAPI(
    title="DLer API",
    description="yt-dlpで動画をダウンロードするAPI",
    version="3.0.0" # Version Bump
)
app.mount("/static", StaticFiles(directory="static"), name="static")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

DOWNLOAD_DIR = "downloads"
DOWNLOAD_DIR_ABSPATH = os.path.abspath(DOWNLOAD_DIR)

# [変更] audio_onlyフラグを追加
class TaskRequest(BaseModel):
    url: HttpUrl
    audio_only: bool = False

def _get_task_details(task_id: str) -> dict:
    task_result = AsyncResult(task_id, app=celery_app)
    status = task_result.status
    
    response_data = {"task_id": task_id, "status": status}

    if task_result.ready():
        result = task_result.result
        if status == 'SUCCESS':
            response_data['details'] = result
            response_data['download_url'] = f"/files/{task_id}"
        elif status == 'FAILURE':
            response_data['details'] = str(result)
            
    return response_data

@app.get("/", response_class=HTMLResponse, summary="フロントエンドページを表示")
def read_root():
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED, summary="動画ダウンロードタスクを作成")
async def create_download_task(request: TaskRequest):
    original_url = str(request.url)
    sanitized_url = original_url.split('&')[0]
    
    # [変更] audio_onlyフラグをCeleryタスクに渡す
    task = download_video.delay(sanitized_url, audio_only=request.audio_only)
    logger.info(f"Task {task.id} created for URL: {sanitized_url} (audio_only={request.audio_only})")
    
    return {"task_id": task.id, "url": sanitized_url}

@app.get("/tasks/{task_id}", summary="タスクの状態を取得")
def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    if not task_result.backend:
        raise HTTPException(status_code=404, detail="Task not found in the backend.")
        
    task_details = _get_task_details(task_id)
    return JSONResponse(content=task_details)

@app.get("/files/{task_id}", summary="ダウンロードしたファイルを取得")
def download_file(task_id: str):
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

@app.delete("/tasks/{task_id}", status_code=status.HTTP_200_OK, summary="個別のタスクと関連ファイルを削除")
def delete_task(task_id: str):
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

    task_result.forget()
    logger.info(f"Deleted task {task_id} from Celery backend.")
    
    return {"status": "deleted", "task_id": task_id}
