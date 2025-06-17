import os
import json
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from celery.result import AsyncResult
import redis

from worker import celery_app, download_video

# --- 初期化 ---
app = FastAPI(
    title="DLer API",
    description="yt-dlpで動画をダウンロードするAPI",
    version="1.7.0"
)
app.mount("/static", StaticFiles(directory="static"), name="static")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# --- 定数 ---
TASK_HISTORY_KEY = "task_history"
MAX_HISTORY_SIZE = 100 # 保存する最大履歴数

class TaskRequest(BaseModel):
    url: HttpUrl

@app.get("/", response_class=HTMLResponse, summary="フロントエンドページを表示")
async def read_root():
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.get("/tasks/history", summary=f"過去{MAX_HISTORY_SIZE}件のタスク履歴を取得")
async def get_tasks_history():
    # lrangeの範囲を0から-1にすることで、常にリスト全体を取得し、ltrimで制限された件数に追従します
    tasks_json = redis_client.lrange(TASK_HISTORY_KEY, 0, -1)
    tasks = []
    for task_str in tasks_json:
        try:
            task_data = json.loads(task_str)
            if isinstance(task_data, dict) and "task_id" in task_data:
                tasks.append(task_data)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode task from history: {task_str}")
            continue

    detailed_tasks = []
    for task_info in tasks:
        task_id = task_info.get("task_id")
        if not task_id:
            continue
        task_result = AsyncResult(task_id, app=celery_app)
        full_details = {
            "task_id": task_id, "url": task_info.get("url"), "status": task_result.status,
        }
        if task_result.successful():
            full_details['details'] = task_result.result
            full_details['download_url'] = f"/files/{task_id}"
        elif task_result.failed():
            # task_result.info はExceptionオブジェクトの場合があるため、str()で変換します
            full_details['details'] = str(task_result.info)
        detailed_tasks.append(full_details)
    return JSONResponse(content=detailed_tasks)

@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED, summary="動画ダウンロードタスクを作成")
async def create_download_task(request: TaskRequest):
    original_url = str(request.url)
    task = download_video.delay(original_url)
    add_task_to_history(task.id, original_url)
    return {"task_id": task.id, "url": original_url}

def add_task_to_history(task_id: str, url: str):
    """
    タスク情報をRedisのリストに保存し、リストのサイズを一定に保つ。

    [修正内容]
    - 不要な `lrem` コマンドを削除しました。
      タスクIDはユニークなため、既存のタスクを削除する必要はありません。
      `lpush`でリストの先頭に追加し、`ltrim`でリストのサイズを制限するだけで十分です。
    """
    task_info = {"task_id": task_id, "url": url}
    redis_client.lpush(TASK_HISTORY_KEY, json.dumps(task_info))
    redis_client.ltrim(TASK_HISTORY_KEY, 0, MAX_HISTORY_SIZE - 1)

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
        raise HTTPException(status_code=404, detail="Task not found, or has failed.")
    result = task_result.get()
    filepath = result.get('filepath')
    original_filename = result.get('original_filename', f'{task_id}.mp4')
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found on the server.")
    return FileResponse(path=filepath, filename=original_filename, media_type='application/octet-stream')

@app.delete("/tasks/{task_id}", status_code=status.HTTP_200_OK, summary="タスクと関連ファイルを削除")
async def delete_task(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)

    # 成功したタスクの場合、関連ファイルを削除
    if task_result.successful():
        filepath = task_result.result.get('filepath')
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError as e:
                # 削除に失敗しても処理は続行するが、ログには残す
                print(f"Error removing file {filepath}: {e}")

    # Redisの履歴リストから該当タスクを削除
    all_tasks_json = redis_client.lrange(TASK_HISTORY_KEY, 0, -1)
    task_to_remove_json = None
    for task_str in all_tasks_json:
        try:
            task_data = json.loads(task_str)
            if task_data.get("task_id") == task_id:
                task_to_remove_json = task_str
                break
        except json.JSONDecodeError:
            continue # 不正なJSONは無視
    
    if task_to_remove_json:
        redis_client.lrem(TASK_HISTORY_KEY, 1, task_to_remove_json)

    # Celeryの結果バックエンドからタスク結果を削除
    task_result.forget()
    
    return {"status": "deleted", "task_id": task_id}
