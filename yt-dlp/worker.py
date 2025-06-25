"""Celeryワーカーを定義し、動画ダウンロードタスクを実行します。

このモジュールは、yt-dlpを使用して指定されたURLから動画をダウンロードする
Celeryタスクを含んでいます。タスクは非同期に実行され、結果はCeleryのバックエンド
（この場合はRedis）に保存されます。
"""
import re
from pathlib import Path
from celery import Task
import yt_dlp

from logger_config import logger
from celery_instance import celery_app  # 独立したインスタンスをインポート

# pathlibを使ってダウンロードディレクトリを定義
APP_DIR = Path(__file__).parent
DOWNLOAD_DIR = APP_DIR / "downloads"


def sanitize_filename(filename: str) -> str:
    """ファイル名として使用できない文字をアンダースコアに置換します。

    Windowsや他のOSで無効な文字を安全な文字に置き換えることで、
    ファイルシステムエラーを防ぎます。
    """
    return re.sub(r'[\\/*?:"<>|]', "_", filename)


@celery_app.task(bind=True, throws=(yt_dlp.utils.DownloadError, Exception))
def download_video(self: Task, url: str) -> dict:
    """指定されたURLから動画を非同期でダウンロードするCeleryタスク。

    yt-dlpを利用して動画をダウンロードし、サーバーの指定ディレクトリに保存します。
    タスクの進捗と結果はCeleryを通じて追跡可能です。

    Args:
        self (Task): Celeryタスクインスタンス。`bind=True`により自動的に渡されます。
        url (str): ダウンロード対象の動画URL。

    Returns:
        dict: ダウンロードが成功した場合、ファイルパスと元のファイル名を含む辞書。

    Raises:
        yt_dlp.utils.DownloadError: yt-dlpが動画のダウンロードに失敗した場合。
        Exception: その他の予期せぬエラーが発生した場合。
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting download for URL: {url}")
    
    output_template = DOWNLOAD_DIR / f'{task_id}.%(ext)s'
    
    ydl_opts = {
        'outtmpl': str(output_template),
        'format': 'bestvideo+bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'postprocessors': [{
            'key': 'FFmpegMetadata',
            'add_metadata': True,
        }],
    }

    try:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info_dict)
            
            title = info_dict.get('title', task_id)
            ext = info_dict.get('ext', 'mp4')
            original_filename = f"{sanitize_filename(title)}.{ext}"

            result_data = {
                'filepath': filepath,
                'original_filename': original_filename
            }
            logger.info(f"[{task_id}] Download successful. File saved at: {filepath}")
            return result_data
            
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"[{task_id}] Failed to download video from {url}. Reason: {e}")
        raise
    except Exception as e:
        logger.error(f"[{task_id}] An unexpected error occurred for URL {url}. Reason: {e}")
        raise
