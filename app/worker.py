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
from celery_instance import celery_app

APP_DIR = Path(__file__).parent
DOWNLOAD_DIR = APP_DIR / "downloads"
YOUTUBE_DOMAINS = ("youtube.com", "youtu.be")

DEFAULT_YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'max_filesize': 5 * 1024 * 1024 * 1024,
    'postprocessors': [{
        'key': 'FFmpegMetadata',
        'add_metadata': True,
    }],
}

def sanitize_filename(filename: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", filename)

@celery_app.task(
    bind=True,
    autoretry_for=(yt_dlp.utils.DownloadError,),
    retry_backoff=60,
    retry_jitter=True,
    max_retries=3,
    throws=(Exception,)
)
def download_video(self: Task, url: str, audio_only: bool = False) -> dict:
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting download for URL: {url}. Attempt: {self.request.retries + 1}")
    
    # yt-dlpが中間ファイルを作成するために、拡張子は動的にしておく
    output_template = DOWNLOAD_DIR / f'{task_id}.%(ext)s'

    ydl_opts = DEFAULT_YDL_OPTS.copy()
    ydl_opts['outtmpl'] = str(output_template)

    if audio_only:
        logger.info(f"[{task_id}] Audio only download requested.")
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        download_format = 'bestvideo+bestaudio/best'
        if any(domain in url for domain in YOUTUBE_DOMAINS):
            logger.info(f"[{task_id}] YouTube URL detected. Using specific format for AVC1/MP4A.")
            download_format = 'bestvideo[vcodec*=avc1]+bestaudio[acodec*=mp4a]/bestvideo+bestaudio/best'
        ydl_opts['format'] = download_format

    try:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            
            # [修正] 最終的なファイルパスを正しく決定する
            if audio_only:
                # 音声変換後は、ファイル名が {task_id}.mp3 になることが分かっている
                filepath = str(DOWNLOAD_DIR / f"{task_id}.mp3")
            else:
                # 動画の場合は、yt-dlpから取得したパスを使用する
                filepath = ydl.prepare_filename(info_dict)

            # 念のため、最終的なファイルが存在するか確認
            if not Path(filepath).exists():
                raise FileNotFoundError(f"Downloaded file not found at expected path: {filepath}")

            title = info_dict.get('title', task_id)
            ext = 'mp3' if audio_only else info_dict.get('ext', 'mp4')
            original_filename = f"{sanitize_filename(title)}.{ext}"

            result_data = {
                'filepath': filepath,
                'original_filename': original_filename
            }
            logger.info(f"[{task_id}] Download successful. File saved at: {filepath}")
            return result_data
            
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"[{task_id}] Failed to download video from {url} after all retries. Reason: {e}")
        raise
    except Exception as e:
        logger.error(f"[{task_id}] An unexpected non-retriable error occurred for URL {url}. Reason: {e}")
        raise
