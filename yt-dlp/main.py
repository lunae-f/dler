import os
import json
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
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
    version="1.3.1"
)
app.mount("/static", StaticFiles(directory="static"), name="static")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def normalize_youtube_url(url: str) -> str:
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    if 'v' in query_params:
        normalized_query = {'v': query_params['v'][0]}
        new_query_string = urlencode(normalized_query)
        return urlunparse(
            (parsed_url.scheme, parsed_url.netloc, parsed_url.path, 
             parsed_url.params, new_query_string, parsed_url.fragment)
        )
    return url

class TaskRequest(BaseModel):
    url: HttpUrl

@app.get("/", response_class=HTMLResponse, summary="フロントエンドページを表示")
async def read_root():
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)


# ★★★★★ ここから修正 ★★★★★
@app.get("/tasks/history", summary="過去10件のタスク履歴を取得")
async def get_tasks_history():
    """
    Redisに保存されているタスク履歴から最新10件を取得します。
    不正な形式のデータは無視して処理を続行します。
    """
    tasks_json = redis_client.lrange("task_history", 0, 9)
    tasks = []
    for task_str in tasks_json:
        try:
            # JSONの解析をtry-exceptブロックで囲む
            task_data = json.loads(task_str)
            if isinstance(task_data, dict) and "task_id" in task_data:
                tasks.append(task_data)
        except json.JSONDecodeError:
            # JSONとして不正なデータがあれば、コンソールに警告を出してスキップ
            print(f"Warning: Could not decode task from history: {task_str}")
            continue

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
# ★★★★★ ここまで修正 ★★★★★


@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED, summary="動画ダウンロードタスクを作成（キャッシュ確認付き）")
async def create_download_task(request: TaskRequest):
    original_url = str(request.url)
    normalized_url = normalize_youtube_url(original_url)

    cached_task_id = redis_client.hget("video_cache", normalized_url)
    if cached_task_id:
        task_result = AsyncResult(cached_task_id, app=celery_app)
        if task_result.successful():
            filepath = task_result.result.get('filepath')
            if filepath and os.path.exists(filepath):
                add_task_to_history(cached_task_id, original_url)
                return {"task_id": cached_task_id, "url": original_url}

    task = download_video.delay(original_url, normalized_url)
    add_task_to_history(task.id, original_url)
    
    return {"task_id": task.id, "url": original_url}

def add_task_to_history(task_id: str, url: str):
    task_info = {"task_id": task_id, "url": url}
    redis_client.lrem("task_history", 0, json.dumps(task_info))
    redis_client.lpush("task_history", json.dumps(task_info))
    redis_client.ltrim("task_history", 0, 99)

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

