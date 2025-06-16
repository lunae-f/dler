import os
import json
# ★ urllib.parseから必要な関数をインポート
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
    version="1.3.0"
)
app.mount("/static", StaticFiles(directory="static"), name="static")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# ★★★★★ ここから追加 ★★★★★
def normalize_youtube_url(url: str) -> str:
    """
    YouTubeのURLから追跡パラメータなどを削除し、'v'パラメータのみに正規化する。
    """
    parsed_url = urlparse(url)
    # URLのクエリパラメータを辞書として解析
    query_params = parse_qs(parsed_url.query)
    
    # 'v'パラメータが存在すれば、それだけを保持
    if 'v' in query_params:
        # 新しいクエリは 'v' パラメータのみ
        normalized_query = {'v': query_params['v'][0]}
        # 新しいクエリ文字列をエンコード
        new_query_string = urlencode(normalized_query)
        # URLを再構築
        return urlunparse(
            (parsed_url.scheme, parsed_url.netloc, parsed_url.path, 
             parsed_url.params, new_query_string, parsed_url.fragment)
        )
    # 'v'パラメータがない、またはYouTube以外のURLの場合はそのまま返す
    return url
# ★★★★★ ここまで追加 ★★★★★

class TaskRequest(BaseModel):
    url: HttpUrl

@app.get("/", response_class=HTMLResponse, summary="フロントエンドページを表示")
async def read_root():
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.get("/tasks/history", summary="過去10件のタスク履歴を取得")
async def get_tasks_history():
    # (この部分は変更なし)
    tasks_json = redis_client.lrange("task_history", 0, 9)
    tasks = [json.loads(task_str) for task_str in tasks_json]
    detailed_tasks = []
    for task_info in tasks:
        task_id = task_info.get("task_id")
        task_result = AsyncResult(task_id, app=celery_app)
        full_details = {
            "task_id": task_id, "url": task_info.get("url"), "status": task_result.status,
        }
        if task_result.successful():
            full_details['details'] = task_result.result
            full_details['download_url'] = f"/files/{task_id}"
        elif task_result.failed():
            full_details['details'] = str(task_result.info)
        detailed_tasks.append(full_details)
    return JSONResponse(content=detailed_tasks)

@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED, summary="動画ダウンロードタスクを作成（キャッシュ確認付き）")
async def create_download_task(request: TaskRequest):
    original_url = str(request.url)
    # ★ URLを正規化してから使用する
    normalized_url = normalize_youtube_url(original_url)

    # 1. 正規化されたURLでキャッシュを確認
    cached_task_id = redis_client.hget("video_cache", normalized_url)
    if cached_task_id:
        task_result = AsyncResult(cached_task_id, app=celery_app)
        if task_result.successful():
            filepath = task_result.result.get('filepath')
            if filepath and os.path.exists(filepath):
                # 有効なキャッシュヒット
                add_task_to_history(cached_task_id, original_url) # 履歴には元のURLを保存
                return {"task_id": cached_task_id, "url": original_url}

    # キャッシュミスの場合、新しいタスクを作成
    # ★ ワーカーには元のURLを渡す
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
    # (この部分は変更なし)
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
    # (この部分は変更なし)
    task_result = AsyncResult(task_id, app=celery_app)
    if not task_result.successful():
        raise HTTPException(status_code=404, detail="Task not found, not completed, or failed.")
    result = task_result.get()
    filepath = result.get('filepath')
    original_filename = result.get('original_filename', f'{task_id}.mp4')
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found on the server.")
    return FileResponse(path=filepath, filename=original_filename, media_type='application/octet-stream')
