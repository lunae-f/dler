import os
import re
import redis
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from celery import Celery, Task
import yt_dlp

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery('tasks', broker=REDIS_URL, backend=REDIS_URL)
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def sanitize_filename(filename: str) -> str:
    """
    ファイル名として不適切な文字をアンダースコアに置換してサニタイズする。
    OSで一般的に禁止されている文字や、パス操作に悪用される可能性のある文字を対象とします。
    """
    # 禁止文字 (/, \, :, *, ?, ", <, >, |) をアンダースコアに置換
    sanitized = re.sub(r'[\\/*?:"<>|]', '_', filename)
    # 制御文字や改行を削除
    sanitized = "".join(c for c in sanitized if c.isprintable())
    # ファイル名の先頭や末尾の空白、ピリオドを削除
    sanitized = sanitized.strip(' .')
    # サニタイズの結果、ファイル名が空になった場合はデフォルト名を返す
    if not sanitized:
        return "untitled"
    return sanitized


def normalize_youtube_url(url: str) -> str:
    """
    YouTubeのURLから追跡パラメータなどを削除し、'v'パラメータのみに正規化する。
    """
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


@celery_app.task(bind=True)
def download_video(self: Task, original_url: str, normalized_url: str) -> dict:
    """
    指定されたURLから動画をダウンロードし、成功時に正規化されたURLをキーとしてキャッシュを作成する。
    """
    task_id = self.request.id
    
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, f'{task_id}.%(ext)s'),
        # H.264(avc1)とAAC(mp4a)を最優先にし、利用できなければ最適なmp4をフォールバックとして選択
        'format': 'bestvideo[vcodec*=avc1]+bestaudio[acodec*=mp4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
    }

    try:
        # ダウンロードには元のURLを使用
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(original_url, download=True)
            filepath = ydl.prepare_filename(info_dict)
            
            # ★★★★★ ここから修正 ★★★★★
            # yt-dlpから取得したタイトルをサニタイズする
            title = info_dict.get('title', task_id)
            sanitized_title = sanitize_filename(title)
            original_filename = f"{sanitized_title}.{info_dict.get('ext', 'mp4')}"
            # ★★★★★ ここまで修正 ★★★★★

            # キャッシュのキーには正規化されたURLを使用
            redis_client.hset("video_cache", normalized_url, task_id)

            result_data = {
                'status': 'COMPLETED',
                'filepath': filepath,
                'original_filename': original_filename
            }
            return result_data
            
    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise e
