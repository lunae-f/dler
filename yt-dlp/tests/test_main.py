import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

@pytest.fixture
def client_and_mocks(mocker):
    """
    TestClientと必要なモックを一度にセットアップするフィクスチャ。
    mainモジュール内のredis_clientとceleryタスクを直接パッチします。
    """
    # 1. Celeryタスクの .delay() メソッドをパッチする
    mock_celery_delay = mocker.patch('main.download_video.delay')
    mock_celery_delay.return_value = MagicMock(id="test-task-id-123")

    # 2. mainモジュール内のredis_clientオブジェクトを直接パッチする
    mock_redis = mocker.patch('main.redis_client')

    # 3. パッチを適用した後に、アプリケーション本体(app)をインポートする
    from main import app
    
    # 4. テストクライアントとモックを生成してテストに渡す
    with TestClient(app) as test_client:
        yield test_client, mock_redis, mock_celery_delay

# --- テストケース ---

def test_read_root(client_and_mocks):
    """ルートパス('/')が正常にHTMLを返すことをテストする"""
    client, _, _ = client_and_mocks
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers['content-type']
    assert "DLer" in response.text

def test_create_download_task(client_and_mocks):
    """'/tasks'へのPOSTリクエストでタスクが正常に作成されることをテストする"""
    client, mock_redis, mock_celery_delay = client_and_mocks
    
    # GIVEN: 正しいリクエストボディと、パイプラインのモック設定
    video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    # WHEN: タスク作成APIをコール
    response = client.post("/tasks", json={"url": video_url})

    # THEN: 正常なレスポンスが返ってくる
    assert response.status_code == 202
    response_data = response.json()
    assert response_data["task_id"] == "test-task-id-123"
    assert response_data["url"] == video_url

    # AND: Celeryタスクが1回呼び出される
    mock_celery_delay.assert_called_once_with(video_url)

    # AND: Redisパイプラインの各コマンドが1回ずつ呼び出される
    mock_pipe.zadd.assert_called_once()
    mock_pipe.hset.assert_called_once()
    mock_pipe.execute.assert_called_once()


def test_get_task_status_success(client_and_mocks, mocker):
    """成功したタスクの状態取得をテストする"""
    client, mock_redis, _ = client_and_mocks
    
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
    mocker.patch('main.AsyncResult', return_value=mock_result)

    # AND: RedisからJSON文字列が返されるように設定
    mock_redis.hget.return_value = '{"url": "http://test.url"}'

    # WHEN: タスク状態取得APIをコール
    response = client.get(f"/tasks/{task_id}")

    # THEN: 正常なレスポンスと詳細情報が返ってくる
    assert response.status_code == 200
    data = response.json()
    assert data['task_id'] == task_id
    assert data['status'] == 'SUCCESS'
    assert data['download_url'] == f"/files/{task_id}"
    assert data['details']['original_filename'] == 'test_video.mp4'


def test_get_task_status_failure(client_and_mocks, mocker):
    """失敗したタスクの状態取得をテストする"""
    client, mock_redis, _ = client_and_mocks
    
    # GIVEN: 失敗状態を模倣したAsyncResultモック
    task_id = "failure-task-id"
    mock_result = MagicMock()
    mock_result.status = 'FAILURE'
    mock_result.successful.return_value = False
    mock_result.ready.return_value = True
    mock_result.result = "DownloadError: This is a test error"
    mocker.patch('main.AsyncResult', return_value=mock_result)
    
    # AND: RedisからJSON文字列が返されるように設定
    mock_redis.hget.return_value = '{"url": "http://failed.url"}'

    # WHEN: タスク状態取得APIをコール
    response = client.get(f"/tasks/{task_id}")

    # THEN: 正常なレスポンスとエラー詳細が返ってくる
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'FAILURE'
    assert "DownloadError" in data['details']


def test_delete_task(client_and_mocks, mocker):
    """タスク削除APIのテスト"""
    client, mock_redis, _ = client_and_mocks
    
    # GIVEN: 削除対象のタスクIDと、パイプラインのモック設定
    task_id = "delete-task-id"
    mock_result = MagicMock()
    mock_result.successful.return_value = True
    mocker.patch('main.AsyncResult', return_value=mock_result)
    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    # WHEN: 削除APIをコール
    response = client.delete(f"/tasks/{task_id}")

    # THEN: 正常なレスポンスが返ってくる
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"

    # AND: Redisパイプラインの各コマンドが1回ずつ呼び出される
    mock_pipe.zrem.assert_called_once_with("task_history:zset", task_id)
    mock_pipe.hdel.assert_called_once_with("task_details:hash", task_id)
    mock_pipe.execute.assert_called_once()
    
    # AND: Celeryの結果が破棄される
    mock_result.forget.assert_called_once()
