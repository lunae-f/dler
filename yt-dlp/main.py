import os
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, HttpUrl
from celery.result import AsyncResult

# worker.py からCeleryアプリケーションとタスクをインポート
from worker import celery_app, download_video

# 1. FastAPIアプリケーションの初期化
app = FastAPI(
    title="yt-dlp API",
    description="yt-dlpで動画をダウンロードするAPI",
    version="1.0.0"
)

# 2. リクエストボディの型定義
#    Pydanticモデルを使い、リクエストの`url`が有効なHTTP URLか検証します。
class TaskRequest(BaseModel):
    url: HttpUrl

# 3. APIエンドポイントの定義

@app.get("/", summary="Health Check")
async def root():
    """
    APIサーバーが正常に起動しているか確認するためのエンドポイント。
    """
    return {"message": "API is running."}


@app.post("/tasks", status_code=status.HTTP_202_ACCEPTED, summary="動画ダウンロードタスクを作成")
async def create_download_task(request: TaskRequest):
    """
    動画のURLを受け取り、バックグラウンドでダウンロードタスクを開始します。
    """
    # `download_video`タスクをCeleryに依頼します。
    # `.delay()` を使うことで、タスクをキューに登録し、即座に制御を返します。
    task = download_video.delay(str(request.url))
    
    # クライアントには、後で状態を確認するための`task_id`を返します。
    return {"task_id": task.id}


@app.get("/tasks/{task_id}", summary="タスクの状態を取得")
async def get_task_status(task_id: str):
    """
    指定されたtask_idの現在の状態（処理中、完了、失敗など）を返します。
    """
    # CeleryのバックエンドからタスクIDに対応する結果を取得
    task_result = AsyncResult(task_id, app=celery_app)
    
    status = task_result.status
    result = task_result.result if task_result.ready() else None
    
    response_data = {
        "task_id": task_id,
        "status": status,
    }

    if status == 'SUCCESS':
        # タスクが成功した場合、結果にダウンロード用URLなどを追加
        response_data['details'] = result
        response_data['download_url'] = f"/files/{task_id}"
    elif status == 'FAILURE':
        # タスクが失敗した場合、結果にエラーメッセージを追加
        response_data['details'] = str(result) # resultには例外情報が入る
    
    # PENDING: まだワーカーに処理されていない
    # PROCESSING (or STARTED): ワーカーが処理中
    return JSONResponse(content=response_data)


@app.get("/files/{task_id}", summary="ダウンロードしたファイルを取得")
async def download_file(task_id: str):
    """
    完了したタスクのIDを指定して、動画ファイルをダウンロードします。
    """
    task_result = AsyncResult(task_id, app=celery_app)

    # タスクが成功裏に完了しているか厳密にチェック
    if not task_result.successful():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Task not found, not completed, or failed."
        )

    result = task_result.get()
    filepath = result.get('filepath')
    original_filename = result.get('original_filename', f'{task_id}.mp4')

    # ファイルがサーバー上に物理的に存在するかチェック
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="File not found on the server. It might have been deleted."
        )

    # FileResponseを使用して、ファイルをクライアントに送信します。
    # `filename`を指定することで、ブラウザがその名前でファイルを保存しようとします。
    return FileResponse(
        path=filepath,
        filename=original_filename,
        media_type='application/octet-stream' # 任意のファイル形式としてダウンロードさせる
    )

