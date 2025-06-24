"""Celeryワーカーを定義し、動画ダウンロードタスクを実行します。

このモジュールは、yt-dlpを使用して指定されたURLから動画をダウンロードする
Celeryタスクを含んでいます。タスクは非同期に実行され、結果はCeleryのバックエンド
（この場合はRedis）に保存されます。
"""
import os
import re
import redis
from celery import Celery, Task
import yt_dlp

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery('tasks', broker=REDIS_URL, backend=REDIS_URL)

DOWNLOAD_DIR = "downloads"


def sanitize_filename(filename: str) -> str:
    """ファイル名として使用できない文字をアンダースコアに置換します。

    Windowsや他のOSで無効な文字を安全な文字に置き換えることで、
    ファイルシステムエラーを防ぎます。

    Args:
        filename (str): サニタイズ対象のファイル名文字列。

    Returns:
        str: サニタイズされたファイル名文字列。
    """
    return re.sub(r'[\\/*?:"<>|]', "_", filename)


@celery_app.task(bind=True, throws=(Exception,))
def download_video(self: Task, url: str) -> dict:
    """指定されたURLから動画を非同期でダウンロードするCeleryタスク。

    yt-dlpを利用して動画をダウンロードし、サーバーの指定ディレクトリに保存します。
    タスクの進捗と結果はCeleryを通じて追跡可能です。

    Args:
        self (Task): Celeryタスクインスタンス。`bind=True`により自動的に渡されます。
        url (str): ダウンロード対象の動画URL。

    Returns:
        dict: ダウンロードが成功した場合、ファイルパスと元のファイル名を含む辞書。
            例: {'filepath': '/app/downloads/task_id.mp4', 'original_filename': 'video_title.mp4'}

    Raises:
        yt_dlp.utils.DownloadError: yt-dlpが動画のダウンロードに失敗した場合
            (例: 動画が存在しない、地域制限、プライベート動画など)。
        Exception: その他の予期せぬエラーが発生した場合。
    """
    task_id = self.request.id
    
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, f'{task_id}.%(ext)s'),
        'format': 'bestvideo[vcodec*=avc1]+bestaudio[acodec*=mp4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # 動画情報を抽出してダウンロードを実行
        info_dict = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info_dict)
        
        # ファイル名をサニタイズ
        title = info_dict.get('title', task_id)
        ext = info_dict.get('ext', 'mp4')
        original_filename = f"{sanitize_filename(title)}.{ext}"

        # 結果を辞書として返す
        result_data = {
            'filepath': filepath,
            'original_filename': original_filename
        }
        return result_data
