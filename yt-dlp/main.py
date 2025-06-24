import os
import json
from typing import List, Optional, Any

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from celery.result import AsyncResult
import redis

from worker import celery_app, download_video, DownloadResult

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
TASK_HISTORY_LIST_KEY = "task_history:list"
TASK_ID_TO_JSON_MAP_KEY = "task_history:id_map"
MAX_HISTORY_SIZE = 100

DOWNLOAD_DIR = "downloads"
DOWNLOAD_DIR_ABSPATH = os.path.abspath(DOWNLOAD_DIR)

# --- Pydanticモデル (APIの型定義) ---
class TaskRequest(BaseModel):
    url: HttpUrl

class TaskCreateResponse(BaseModel):
    task_id: str
    url: HttpUrl

class TaskStatusResponse(BaseModel):
    task_id: str
    url: Optional[HttpUrl] = None
    status: str
    # 成功時はDownloadResult、失敗時はstr(Exception)が入るためAnyを使用
    details: Optional[Any] = None
    download_url: Optional[str] = None


# --- APIエンドポイント ---

@app.get("/", response_class=HTMLResponse, summary="フロントエンドページを表示")
async def read_root():
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.get("/tasks/history", response_model=List[TaskStatusResponse], summary=f"過去{MAX_HISTORY_SIZE}件のタスク履歴を取得")
async def get_tasks_history():
    tasks_json = redis_client.lrange(TASK_HISTORY_LIST_KEY, 0, -1)
    tasks = [json.loads(task_str) for task_str in tasks_json]
    
    detailed_tasks = []
    for task_info in tasks:
        task_id = task_info.get("task_id")
        if not task_id:
            continue
        
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
        
    return detailed_tasks

@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED, response_model=TaskCreateResponse, summary="動画ダウンロードタスクを作成")
async def create_download_task(request: TaskRequest):
    original_url = str(request.url)
    task = download_video.delay(original_url)
    add_task_to_history(task.id, original_url)
    return {"task_id": task.id, "url": original_url}

@app.get("/tasks/{task_id}", response_model=TaskStatusResponse, summary="タスクの状態を取得")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    status = task_result.status

    task_info_json = redis_client.hget(TASK_ID_TO_JSON_MAP_KEY, task_id)
    url = json.loads(task_info_json).get("url") if task_info_json else None
    
    response_data = {"task_id": task_id, "status": status, "url": url}
    
    if task_result.ready():
        if status == 'SUCCESS':
            response_data['details'] = task_result.result
            response_data['download_url'] = f"/files/{task_id}"
        elif status == 'FAILURE':
            response_data['details'] = str(task_result.result)
            
    return response_data

@app.get("/files/{task_id}", summary="ダウンロードしたファイルを取得")
async def download_file(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    if not task_result.successful():
        raise HTTPException(status_code=404, detail="Task not found, or has failed.")
    
    result: DownloadResult = task_result.get()
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
    task_result = AsyncResult(task_id, app=celery_app)

    if task_result.successful():
        result = task_result.result or {}
        filepath = result.get('filepath')
        if filepath and os.path.exists(filepath):
            try:
                file_to_delete_abspath = os.path.abspath(filepath)
                if file_to_delete_abspath.startswith(DOWNLOAD_DIR_ABSPATH):
                    os.remove(file_to_delete_abspath)
            except OSError as e:
                print(f"Error removing file {filepath}: {e}")

    task_to_remove_json = redis_client.hget(TASK_ID_TO_JSON_MAP_KEY, task_id)

    if task_to_remove_json:
        pipe = redis_client.pipeline()
        pipe.lrem(TASK_HISTORY_LIST_KEY, 1, task_to_remove_json)
        pipe.hdel(TASK_ID_TO_JSON_MAP_KEY, task_id)
        pipe.execute()

    task_result.forget()
    
    return {"status": "deleted", "task_id": task_id}


# --- ヘルパー関数 ---
def add_task_to_history(task_id: str, url: str):
    # (この関数の内容は変更ありません)
    task_info = {"task_id": task_id, "url": url}
    task_json = json.dumps(task_info)
    
    pipe = redis_client.pipeline()
    pipe.lpush(TASK_HISTORY_LIST_KEY, task_json)
    pipe.hset(TASK_ID_TO_JSON_MAP_KEY, task_id, task_json)
    pipe.ltrim(TASK_HISTORY_LIST_KEY, 0, MAX_HISTORY_SIZE - 1)
    pipe.execute()
    
    current_ids_in_list = {json.loads(s)['task_id'] for s in redis_client.lrange(TASK_HISTORY_LIST_KEY, 0, -1)}
    all_ids_in_map = redis_client.hkeys(TASK_ID_TO_JSON_MAP_KEY)
    
    ids_to_remove_from_map = [map_id for map_id in all_ids_in_map if map_id not in current_ids_in_list]
    if ids_to_remove_from_map:
        redis_client.hdel(TASK_ID_TO_JSON_MAP_KEY, *ids_to_remove_from_map)
