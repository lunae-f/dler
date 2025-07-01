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

# デフォルトオプションに writethumbnail を追加
DEFAULT_YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'max_filesize': 5 * 1024 * 1024 * 1024,
    'writethumbnail': True,  # サムネイルをディスクに書き出す
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
    
    output_template = DOWNLOAD_DIR / f'{task_id}.%(ext)s'

    ydl_opts = DEFAULT_YDL_OPTS.copy()
    ydl_opts['outtmpl'] = str(output_template)

    # [修正] ポストプロセッサのベースを定義
    postprocessors = [
        {'key': 'FFmpegMetadata', 'add_metadata': True}, # メタデータを追加
    ]

    if audio_only:
        logger.info(f"[{task_id}] Audio only download requested.")
        ydl_opts['format'] = 'bestaudio/best'
        # 音声抽出のポストプロセッサを追加
        postprocessors.append({
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        })
    else:
        # 動画のフォーマット設定
        download_format = 'bestvideo+bestaudio/best'
        if any(domain in url for domain in YOUTUBE_DOMAINS):
            logger.info(f"[{task_id}] YouTube URL detected. Using specific format for AVC1/MP4A.")
            download_format = 'bestvideo[vcodec*=avc1]+bestaudio[acodec*=mp4a]/bestvideo+bestaudio/best'
        ydl_opts['format'] = download_format

    # 最後にサムネイル埋め込みのポストプロセッサを追加
    postprocessors.append({'key': 'EmbedThumbnail', 'already_have_thumbnail': False})
    
    ydl_opts['postprocessors'] = postprocessors

    try:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            
            if audio_only:
                filepath = str(DOWNLOAD_DIR / f"{task_id}.mp3")
            else:
                filepath = ydl.prepare_filename(info_dict)

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
