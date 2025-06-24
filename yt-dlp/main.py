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

from worker import celery_app, download_video

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
# ZSETでタスクIDをタイムスタンプ順に管理し、HASHで詳細を管理する
TASK_HISTORY_ZSET_KEY = "task_history:zset"
TASK_DETAILS_HASH_KEY = "task_details:hash"
MAX_HISTORY_SIZE = 100

DOWNLOAD_DIR = "downloads"
DOWNLOAD_DIR_ABSPATH = os.path.abspath(DOWNLOAD_DIR)

class TaskRequest(BaseModel):
    url: HttpUrl

@app.get("/", response_class=HTMLResponse, summary="フロントエンドページを表示")
async def read_root():
    """フロントエンドのメインページ (index.html) を返します。

    Returns:
        HTMLResponse: index.htmlの内容を持つHTMLレスポンス。
    """
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.get("/tasks/history", summary=f"過去{MAX_HISTORY_SIZE}件のタスク履歴を取得")
async def get_tasks_history():
    """過去のタスク履歴を最大件数まで取得します。

    Redisに保存されているタスクIDを新しい順に取得し、各タスクの最新の状態を
    Celeryバックエンドから問い合わせて付与したリストを返します。

    Returns:
        JSONResponse: 成功したタスク、失敗したタスク、処理中のタスクの
                      詳細情報を含むリスト。
    """
    # ZSETからタスクIDを新しい順に取得
    task_ids = redis_client.zrevrange(TASK_HISTORY_ZSET_KEY, 0, MAX_HISTORY_SIZE - 1)
    if not task_ids:
        return JSONResponse(content=[])

    # HASHからタスクの詳細を一括取得
    tasks_details_json = redis_client.hmget(TASK_DETAILS_HASH_KEY, task_ids)

    detailed_tasks = []
    for task_id, task_detail_json in zip(task_ids, tasks_details_json):
        task_result = AsyncResult(task_id, app=celery_app)
        
        url = None
        if task_detail_json:
            try:
                url = json.loads(task_detail_json).get("url")
            except (json.JSONDecodeError, TypeError):
                print(f"Warning: Could not decode task detail for {task_id}")

        full_details = {
            "task_id": task_id, "url": url, "status": task_result.status,
        }
        if task_result.successful():
            full_details['details'] = task_result.result
            full_details['download_url'] = f"/files/{task_id}"
        elif task_result.failed():
            full_details['details'] = str(task_result.info)
        
        detailed_tasks.append(full_details)
        
    return JSONResponse(content=detailed_tasks)

@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED, summary="動画ダウンロードタスクを作成")
async def create_download_task(request: TaskRequest):
    """新しい動画ダウンロードタスクを作成します。

    リクエストボディで受け取ったURLを基に、Celeryワーカーにダウンロードタスクを
    非同期で依頼します。

    Args:
        request (TaskRequest): ダウンロードしたい動画のURLを含むリクエストボディ。

    Returns:
        dict: 作成されたタスクのIDと元のURL。
    """
    original_url = str(request.url)
    task = download_video.delay(original_url)
    add_task_to_history(task.id, original_url)
    return {"task_id": task.id, "url": original_url}

def add_task_to_history(task_id: str, url: str):
    """Redisにタスク情報を追加するヘルパー関数。

    新しいタスクの情報をRedisのZSETとHASHに保存します。
    ZSETのサイズは一定に保たれ、古いものから削除されます。
    HASHに孤児データが残らないよう、クリーンアップも行います。

    Args:
        task_id (str): 保存するタスクのID。
        url (str): 保存するタスクの元のURL。
    """
    pipe = redis_client.pipeline()
    timestamp = time.time()
    task_details = json.dumps({"url": url})
    
    # 新しいタスクをZSETとHASHに追加
    pipe.zadd(TASK_HISTORY_ZSET_KEY, {task_id: timestamp})
    pipe.hset(TASK_DETAILS_HASH_KEY, task_id, task_details)
    
    # ZSETのサイズを制限し、古いエントリを削除
    pipe.zremrangebyrank(TASK_HISTORY_ZSET_KEY, 0, -MAX_HISTORY_SIZE - 1)
    
    pipe.execute()
    
    # HASH内の孤児エントリをクリーンアップ (ZSETに存在しないものを削除)
    current_ids_in_zset = redis_client.zrange(TASK_HISTORY_ZSET_KEY, 0, -1)
    all_ids_in_hash = redis_client.hkeys(TASK_DETAILS_HASH_KEY)
    
    ids_to_remove_from_hash = [hash_id for hash_id in all_ids_in_hash if hash_id not in current_ids_in_zset]
    if ids_to_remove_from_hash:
        redis_client.hdel(TASK_DETAILS_HASH_KEY, *ids_to_remove_from_hash)

@app.get("/tasks/{task_id}", summary="タスクの状態を取得")
async def get_task_status(task_id: str):
    """指定されたタスクIDの状態と詳細を取得します。

    Args:
        task_id (str): 状態を確認したいタスクのID。

    Returns:
        JSONResponse: タスクのID、状態、URL、および成功/失敗時の詳細情報。
    """
    task_result = AsyncResult(task_id, app=celery_app)
    status = task_result.status

    # HASHからURLを直接取得
    task_info_json = redis_client.hget(TASK_DETAILS_HASH_KEY, task_id)
    url = json.loads(task_info_json).get("url") if task_info_json else None
    
    response_data = {"task_id": task_id, "status": status, "url": url}
    
    if task_result.ready():
        result = task_result.result
        if status == 'SUCCESS':
            response_data['details'] = result
            response_data['download_url'] = f"/files/{task_id}"
        elif status == 'FAILURE':
            response_data['details'] = str(result)
            
    return JSONResponse(content=response_data)

@app.get("/files/{task_id}", summary="ダウンロードしたファイルを取得")
async def download_file(task_id: str):
    """ダウンロード済みのファイルを取得します。

    タスクが成功している場合のみ、関連付けられた動画ファイルを返します。

    Args:
        task_id (str): ダウンロードしたいファイルのタスクID。

    Returns:
        FileResponse: 動画ファイル。

    Raises:
        HTTPException(404): タスクが見つからない、失敗している、または
                           ファイルがサーバー上に存在しない場合。
        HTTPException(403): ファイルパスが許可されたディレクトリ外にある場合
                           (パストラバーサル対策)。
    """
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
    """タスク履歴と関連するダウンロード済みファイルを削除します。

    タスクが成功している場合は、まずディスク上のファイルを削除します。
    その後、Redis上のタスク履歴とCeleryの結果を削除します。

    Args:
        task_id (str): 削除したいタスクのID。

    Returns:
        dict: 削除が実行されたことを示すステータス。
    """
    task_result = AsyncResult(task_id, app=celery_app)

    if task_result.successful():
        result = task_result.result or {}
        filepath = result.get('filepath')
        if filepath and os.path.exists(filepath):
            try:
                # ここでもファイルパスを検証することがより安全
                file_to_delete_abspath = os.path.abspath(filepath)
                if file_to_delete_abspath.startswith(DOWNLOAD_DIR_ABSPATH):
                    os.remove(file_to_delete_abspath)
            except OSError as e:
                print(f"Error removing file {filepath}: {e}") # ロガーに置き換えるのが望ましい

    # RedisからZSETとHASHのエントリを削除
    pipe = redis_client.pipeline()
    pipe.zrem(TASK_HISTORY_ZSET_KEY, task_id)
    pipe.hdel(TASK_DETAILS_HASH_KEY, task_id)
    pipe.execute()

    # Celeryバックエンドから結果を削除
    task_result.forget()
    
    return {"status": "deleted", "task_id": task_id}
