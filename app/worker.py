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

# --- 定数定義 ---
APP_DIR = Path(__file__).parent
DOWNLOAD_DIR = APP_DIR / "downloads"
YOUTUBE_DOMAINS = ("youtube.com", "youtu.be")

# [改善] yt-dlpのデフォルト設定を分離
# ファイルサイズの上限を5GBに設定 (Noneにすれば無制限)
DEFAULT_YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'max_filesize': 5 * 1024 * 1024 * 1024,  # 5GB
    'postprocessors': [{
        'key': 'FFmpegMetadata',
        'add_metadata': True,
    }],
}

def sanitize_filename(filename: str) -> str:
    """ファイル名として使用できない文字をアンダースコアに置換します。

    Windowsや他のOSで無効な文字を安全な文字に置き換えることで、
    ファイルシステムエラーを防ぎます。
    """
    return re.sub(r'[\\/*?:"<>|]', "_", filename)


# [改善] 自動リトライ機能を追加
# DownloadErrorが発生した場合、最大3回まで、最初は60秒後、次は120秒後...と間隔を空けてリトライ
@celery_app.task(
    bind=True,
    autoretry_for=(yt_dlp.utils.DownloadError,),
    retry_backoff=60,
    retry_jitter=True,
    max_retries=3,
    throws=(Exception,)
)
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
        yt_dlp.utils.DownloadError: yt-dlpが動画のダウンロードに失敗した場合（リトライ後）。
        Exception: その他の予期せぬエラーが発生した場合。
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting download for URL: {url}. Attempt: {self.request.retries + 1}")
    
    output_template = DOWNLOAD_DIR / f'{task_id}.%(ext)s'
    
    # yt-dlpのオプションをコピーして設定
    ydl_opts = DEFAULT_YDL_OPTS.copy()
    ydl_opts['outtmpl'] = str(output_template)

    # デフォルトのフォーマット
    download_format = 'bestvideo+bestaudio/best'
    
    # [改善] anyとジェネレータ式でURL判定をよりクリーンに
    if any(domain in url for domain in YOUTUBE_DOMAINS):
        logger.info(f"[{task_id}] YouTube URL detected. Using specific format for AVC1/MP4A.")
        download_format = 'bestvideo[vcodec*=avc1]+bestaudio[acodec*=mp4a]/bestvideo+bestaudio/best'
    
    ydl_opts['format'] = download_format

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
        logger.error(f"[{task_id}] Failed to download video from {url} after all retries. Reason: {e}")
        raise  # Celeryがリトライを処理するために再度raiseする
    except Exception as e:
        logger.error(f"[{task_id}] An unexpected non-retriable error occurred for URL {url}. Reason: {e}")
        # タスクの状態をFAILUREに更新するために、手動で状態を更新することも可能
        # self.update_state(state='FAILURE', meta={'exc_type': type(e).__name__, 'exc_message': str(e)})
        raise
