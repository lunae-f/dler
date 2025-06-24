import pytest
from playwright.sync_api import Page, expect, Route

# テスト対象のベースURL
BASE_URL = "http://localhost:8000"

def test_initial_page_load(page: Page):
    """ページが正しく読み込まれ、主要な要素が表示されることを確認する"""
    page.goto(BASE_URL)
    
    # <h1>タグに'DLer'というテキストが含まれていることを期待する
    expect(page.locator("h1")).to_have_text("DLer")
    
    # URL入力欄が表示されていることを期待する
    expect(page.get_by_placeholder("https://www.youtube.com/watch?v=...")).to_be_visible()
    
    # 送信ボタンが表示されていることを期待する
    expect(page.get_by_role("button", name="ダウンロード開始")).to_be_visible()

def test_add_new_task(page: Page):
    """URLを入力してタスクを追加すると、リストに表示されることをテストする"""
    
    # --- GIVEN (前提条件): テスト用のURLとモックAPIの設定 ---
    video_url = "https://www.youtube.com/watch?v=test-video"
    mock_task_id = "frontend-test-123"

    # フロントエンドが "/tasks" にPOSTリクエストを送った際のレスポンスをモックする
    # これにより、バックエンドが実際に動作していなくてもテストが可能になる
    def handle_route(route: Route):
        # どのリクエストにも固定のJSONを返す
        response_json = {"task_id": mock_task_id, "url": video_url}
        route.fulfill(status=202, json=response_json)

    # ページのネットワークリクエストを監視し、'/tasks' へのPOSTだけを差し替える
    page.route(f"{BASE_URL}/tasks", handle_route, times=1)
    
    # --- WHEN (操作): ユーザーの操作をシミュレート ---
    # 1. ページを開く
    page.goto(BASE_URL)
    
    # 2. URL入力欄にテスト用のURLを入力する
    page.get_by_placeholder("https://www.youtube.com/watch?v=...").fill(video_url)
    
    # 3. "ダウンロード開始" ボタンをクリックする
    page.get_by_role("button", name="ダウンロード開始").click()
    
    # --- THEN (結果確認): UIの変更を確認 ---
    
    # 1. 新しく作成されたタスクのリスト項目を探す
    new_task_item = page.locator(f"#task-{mock_task_id}")
    
    # 2. そのリスト項目が表示されることを期待する (非同期で表示されるため、少し待機する)
    expect(new_task_item).to_be_visible(timeout=5000)
    
    # 3. リスト項目の中に、入力したURLのテキストが含まれていることを期待する
    expect(new_task_item).to_contain_text(video_url)

