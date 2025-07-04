import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

@pytest.fixture
def client_and_mocks(mocker):
    """
    TestClientとCeleryタスクのモックをセットアップするフィクスチャ。
    """
    # Celeryタスクの .delay() メソッドをパッチする
    mock_celery_delay = mocker.patch('main.download_video.delay')
    mock_celery_delay.return_value = MagicMock(id="test-task-id-123")

    # mainモジュールをインポートする（パッチ後）
    from main import app
    
    with TestClient(app) as test_client:
        yield test_client, mock_celery_delay

# --- テストケース ---

def test_read_root(client_and_mocks):
    """ルートパス('/')が正常にHTMLを返すことをテストする"""
    client, _ = client_and_mocks
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers['content-type']
    assert "DLer" in response.text

def test_create_download_task(client_and_mocks):
    """'/tasks'へのPOSTリクエストでタスクが正常に作成されることをテストする"""
    client, mock_celery_delay = client_and_mocks
    
    # GIVEN: 正しいリクエストボディ
    video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # WHEN: タスク作成APIをコール
    # audio_onlyを指定しないリクエストをシミュレート
    response = client.post("/tasks", json={"url": video_url})

    # THEN: 正常なレスポンスが返ってくる
    assert response.status_code == 202
    response_data = response.json()
    assert response_data["task_id"] == "test-task-id-123"
    assert response_data["url"] == video_url

    # AND: Celeryタスクが1回呼び出される
    # [修正] audio_only=False がデフォルトで渡されることを検証する
    mock_celery_delay.assert_called_once_with(video_url, audio_only=False)


@patch('main.AsyncResult')
def test_get_task_status_success(mock_async_result, client_and_mocks):
    """成功したタスクの状態取得をテストする"""
    client, _ = client_and_mocks
    
    # GIVEN: 成功状態を模倣したAsyncResultモック
    task_id = "success-task-id"
    mock_result = MagicMock()
    mock_result.status = 'SUCCESS'
    mock_result.successful.return_value = True
    mock_result.ready.return_value = True
    mock_result.result = {
        'filepath': f'/app/downloads/{task_id}.mp4',
        'original_filename': 'test_video.mp4'
    }
    mock_async_result.return_value = mock_result

    # WHEN: タスク状態取得APIをコール
    response = client.get(f"/tasks/{task_id}")

    # THEN: 正常なレスポンスと詳細情報が返ってくる
    assert response.status_code == 200
    data = response.json()
    assert data['task_id'] == task_id
    assert data['status'] == 'SUCCESS'
    assert data['download_url'] == f"/files/{task_id}"
    assert data['details']['original_filename'] == 'test_video.mp4'


@patch('main.AsyncResult')
def test_get_task_status_failure(mock_async_result, client_and_mocks):
    """失敗したタスクの状態取得をテストする"""
    client, _ = client_and_mocks
    
    # GIVEN: 失敗状態を模倣したAsyncResultモック
    task_id = "failure-task-id"
    mock_result = MagicMock()
    mock_result.status = 'FAILURE'
    mock_result.successful.return_value = False
    mock_result.ready.return_value = True
    mock_result.result = "DownloadError: This is a test error"
    mock_async_result.return_value = mock_result
    
    # WHEN: タスク状態取得APIをコール
    response = client.get(f"/tasks/{task_id}")

    # THEN: 正常なレスポンスとエラー詳細が返ってくる
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'FAILURE'
    assert "DownloadError" in data['details']


@patch('main.AsyncResult')
@patch('main.os')
def test_delete_task(mock_os, mock_async_result, client_and_mocks):
    """タスク削除APIのテスト（ファイル削除も含む）"""
    client, _ = client_and_mocks
    
    # GIVEN: 削除対象のタスクIDと、ファイルパスを含む成功したタスク結果のモック
    task_id = "delete-task-id"
    file_path = "/app/downloads/delete-task-id.mp4"
    
    mock_result = MagicMock()
    mock_result.successful.return_value = True
    mock_result.result = {'filepath': file_path}
    mock_async_result.return_value = mock_result
    
    mock_os.path.exists.return_value = True
    # abspathとstartswithのチェックを通過させるための設定
    mock_os.path.abspath.side_effect = lambda p: p 
    # main.DOWNLOAD_DIR_ABSPATH が /app/downloads であることを前提とする
    
    # WHEN: 削除APIをコール
    response = client.delete(f"/tasks/{task_id}")

    # THEN: 正常なレスポンスが返ってくる
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"

    # AND: ファイル削除処理が呼び出される
    mock_os.remove.assert_called_once_with(file_path)
    
    # AND: Celeryの結果が破棄される
    mock_result.forget.assert_called_once()
