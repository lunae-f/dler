# app/main.py
import os
import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, BackgroundTasks, HTTPException, Path
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# --- 定数定義 ---
DOWNLOADS_DIR = "downloads"
# タスクの状態を管理するインメモリの辞書
# 本番環境ではRedisやデータベースを推奨
tasks: Dict[str, Dict[str, Any]] = {}

# --- FastAPIのライフサイクル管理 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # アプリケーション起動時に実行
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    yield
    # アプリケーション終了時に実行 (今回はクリーンアップ処理なし)

# --- FastAPIアプリケーションの初期化 ---
app = FastAPI(
    title="yt-dlp API Server",
    description="A server to download videos using yt-dlp with parallel processing capabilities.",
    version="1.0.0",
    lifespan=lifespan
)

# --- リクエスト/レスポンスモデルの定義 (Pydantic) ---
class YtDlpOptions(BaseModel):
    format: Optional[str] = Field(None, description="Video/audio format (e.g., 'best', 'mp4')")
    audio_only: bool = Field(False, description="Download audio only")
    output_template: str = Field(f"{DOWNLOADS_DIR}/%(title)s [%(id)s].%(ext)s", description="Output filename template")

class DownloadRequest(BaseModel):
    url: str = Field(..., description="URL of the video to download")
    options: Optional[YtDlpOptions] = Field(default_factory=YtDlpOptions)

class DownloadResponse(BaseModel):
    message: str
    task_id: str

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    details: Optional[str] = None
    result: Optional[Dict[str, List[str]]] = None


# --- バックグラウンド処理関数 ---
async def run_yt_dlp(task_id: str, url: str, options: YtDlpOptions):
    """
    yt-dlpをサブプロセスとして非同期で実行する
    """
    tasks[task_id]["status"] = "processing"
    tasks[task_id]["details"] = f"Starting download for {url}"

    # yt-dlpのコマンドを構築
    # セキュリティのため、引数は慎重に扱う
    cmd = [
        "yt-dlp",
        "--no-progress",
        "--no-warnings",
        # JSON形式で進捗や結果を出力させ、後からパースする
        "--print", "json",
    ]

    # オプションを追加
    if options.audio_only:
        cmd.extend(["-f", "bestaudio/best", "-x"])
    elif options.format:
        cmd.extend(["-f", options.format])

    # 出力先テンプレート
    cmd.extend(["-o", options.output_template])
    
    cmd.append(url)

    # サブプロセスを非同期で実行
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()
    
    if process.returncode == 0:
        try:
            # yt-dlpの最後の標準出力行はJSON情報
            last_line = stdout.decode().strip().split('\n')[-1]
            info = json.loads(last_line)
            
            filepath = info.get("_filename") or f"{DOWNLOADS_DIR}/{info.get('title')}.{info.get('ext')}"
            filename = os.path.basename(filepath)

            tasks[task_id]["status"] = "completed"
            tasks[task_id]["details"] = "Download finished successfully."
            tasks[task_id]["result"] = {
                "files": [filename],
                "download_urls": [f"/downloads/{filename}"]
            }
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            tasks[task_id]["status"] = "error"
            tasks[task_id]["details"] = f"Failed to parse yt-dlp output. Error: {str(e)}. Raw output: {stdout.decode()}"

    else:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["details"] = f"yt-dlp failed with return code {process.returncode}. Error: {stderr.decode()}"


# --- APIエンドポイント ---
@app.post("/api/v1/download", response_model=DownloadResponse, status_code=202)
async def create_download_task(
    request: DownloadRequest,
    background_tasks: BackgroundTasks
):
    """
    ダウンロードタスクを作成し、バックグラウンドで処理を開始する
    """
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "pending",
        "details": "Task is waiting to be processed."
    }
    
    # yt-dlpの実行をバックグラウンドタスクとして追加
    background_tasks.add_task(run_yt_dlp, task_id, request.url, request.options)
    
    return {"message": "Download task created successfully.", "task_id": task_id}


@app.get("/api/v1/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str = Path(..., description="The ID of the task to check")):
    """
    指定されたタスクIDの現在のステータスを返す
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskStatusResponse(task_id=task_id, **task)

# 静的ファイル配信のためのマウント
# これにより /downloads/{filename} でファイルにアクセスできる
app.mount("/downloads", StaticFiles(directory=DOWNLOADS_DIR), name="downloads")


@app.get("/", include_in_schema=False)
async def root():
    return JSONResponse(
        content={"message": "Welcome to the yt-dlp API server. See /docs for API documentation."}
    )

# yt-dlpからの出力をパースするためにjsonライブラリをインポート
import json
