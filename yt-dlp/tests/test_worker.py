import pytest
from unittest.mock import MagicMock, patch
import yt_dlp

from worker import download_video, sanitize_filename
from celery_instance import celery_app

# Celeryをテスト用に設定します。
# `task_always_eager=True`にすると、タスクが非同期ではなく同期的に実行されるため、
# `.delay()`を呼び出すとすぐにタスクが完了し、テスト内で結果を直接検証できます。
@pytest.fixture(scope="module", autouse=True)
def setup_celery_for_testing():
    """テスト実行中、Celeryを同期モードで動作させるためのフィクスチャ。"""
    celery_app.conf.update(
        task_always_eager=True,
        # task_eager_propagates=True の設定を削除(またはFalseに)することで、
        # タスク内の例外がテストをクラッシュさせるのを防ぎます。
    )

# --- テストケース ---

def test_sanitize_filename():
    """
    ファイル名からOSで無効な文字が正しくサニタイズされるかをテストします。
    """
    # 期待値を実際の実装の出力に合わせます。
    assert sanitize_filename('my:file/name?is*<"bad">|') == "my_file_name_is___bad___"
    assert sanitize_filename("A normal filename.mp4") == "A normal filename.mp4"
    assert sanitize_filename("") == ""

@patch('worker.yt_dlp.YoutubeDL')
def test_download_video_success(mock_youtube_dl):
    """
    `download_video`タスクが正常に完了するケースをテストします。

    `yt-dlp`ライブラリの呼び出しをモック化し、タスクが成功ステータスになり、
    期待される形式の辞書（ファイルパスと元のファイル名）を返すことを確認します。
    """
    # --- GIVEN (前提条件): モックとテストデータの設定 ---
    video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    task_id = "test-success-id"
    expected_filepath = f"/app/downloads/{task_id}.mp4"
    expected_title = "Test Video Title"
    
    # `yt_dlp.YoutubeDL`のコンテキストマネージャ(`__enter__`)が返すインスタンスをモックします。
    mock_ydl_instance = MagicMock()
    
    # `extract_info`メソッドが返すダミーの動画情報を設定します。
    mock_info_dict = {
        'title': expected_title,
        'ext': 'mp4',
    }
    mock_ydl_instance.extract_info.return_value = mock_info_dict
    
    # `prepare_filename`メソッドが返すダミーのファイルパスを設定します。
    mock_ydl_instance.prepare_filename.return_value = expected_filepath
    
    # `with yt_dlp.YoutubeDL(...) as ydl:` の部分が、設定したモックを返すようにします。
    mock_youtube_dl.return_value.__enter__.return_value = mock_ydl_instance

    # --- WHEN (操作): Celeryタスクを同期的に実行します ---
    # .apply() を使うことで、テスト内でタスクIDを明示的に設定できます。
    result = download_video.apply(args=[video_url], task_id=task_id)

    # --- THEN (結果確認) ---
    # 1. タスクが成功したことを確認します。
    assert result.successful()
    assert result.state == 'SUCCESS'
    
    # 2. タスクの返り値が正しいか確認します。
    task_output = result.get()
    assert task_output['filepath'] == expected_filepath
    assert task_output['original_filename'] == f"{sanitize_filename(expected_title)}.mp4"

    # 3. `yt-dlp`の各メソッドが期待通りに呼び出されたか確認します。
    mock_youtube_dl.assert_called_once() # YoutubeDL()が呼ばれたか
    mock_ydl_instance.extract_info.assert_called_once_with(video_url, download=True)
    mock_ydl_instance.prepare_filename.assert_called_once_with(mock_info_dict)


@patch('worker.yt_dlp.YoutubeDL')
def test_download_video_failure(mock_youtube_dl):
    """
    `download_video`タスクが`yt-dlp`の例外により失敗するケースをテストします。

    タスクが'FAILURE'状態になり、例外情報が正しく保存されることを確認します。
    """
    # --- GIVEN (前提条件): モックの設定 ---
    video_url = "https://www.youtube.com/watch?v=invalid-url"
    
    # `extract_info`メソッドが`DownloadError`を発生するように設定します。
    mock_ydl_instance = MagicMock()
    error_message = "Test download error"
    mock_ydl_instance.extract_info.side_effect = yt_dlp.utils.DownloadError(error_message)
    mock_youtube_dl.return_value.__enter__.return_value = mock_ydl_instance

    # --- WHEN (操作): Celeryタスクを同期的に実行します ---
    # Celeryの設定変更により、ここでの例外はテストをクラッシュさせなくなります。
    result = download_video.delay(video_url)

    # --- THEN (結果確認) ---
    # 1. タスクが失敗したことを確認します。
    assert result.failed()
    assert result.state == 'FAILURE'
    
    # 2. 結果に例外情報が含まれているか確認します。
    assert isinstance(result.result, yt_dlp.utils.DownloadError)
    assert error_message in str(result.result)
