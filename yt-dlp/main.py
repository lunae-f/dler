import os
from fastapi import FastAPI, HTTPException, status
# 必要なモジュールを追加
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from celery.result import AsyncResult

# worker.py からCeleryアプリケーションとタスクをインポート
from worker import celery_app, download_video

# 1. FastAPIアプリケーションの初期化
app = FastAPI(
    title="DLer API",
    description="yt-dlpで動画をダウンロードするAPI",
    version="1.0.0"
)

# "static"ディレクトリをマウントして、CSSやJSファイルにアクセスできるようにする
app.mount("/static", StaticFiles(directory="static"), name="static")


# 2. リクエストボディの型定義
class TaskRequest(BaseModel):
    url: HttpUrl

# 3. APIエンドポイントの定義
@app.get("/", response_class=HTMLResponse, summary="フロントエンドページを表示")
async def read_root():
    """
    アプリケーションのメインページ(index.html)を返します。
    """
    # index.htmlを読み込んでレスポンスとして返す
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)


@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED, summary="動画ダウンロードタスクを作成")
async def create_download_task(request: TaskRequest):
    task = download_video.delay(str(request.url))
    return {"task_id": task.id}


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
