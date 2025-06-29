document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('url-form');
    const urlInput = document.getElementById('video-url');
    const submitButton = form.querySelector('button[type="submit"]');
    const statusContainer = document.getElementById('status-container');
    const downloadLinkContainer = document.getElementById('download-link-container');

    let pollingInterval = null;

    /**
     * フォームの送信イベントを処理します。
     */
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = urlInput.value;
        if (!url) return;

        // 以前の表示をクリアし、フォームを無効化
        clearStatusAndLink();
        setFormDisabled(true);
        showStatus('処理中...', 'processing');

        try {
            const response = await fetch('/tasks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });
            if (!response.ok) throw new Error('タスクの作成に失敗しました。');
            const data = await response.json();
            startPolling(data.task_id);
        } catch (error) {
            console.error(error);
            showStatus(`エラー: ${error.message}`, 'failure');
            setFormDisabled(false);
        }
    });

    /**
     * 指定されたタスクIDのポーリングを開始します。
     * @param {string} taskId - タスクID
     */
    function startPolling(taskId) {
        if (pollingInterval) {
            clearInterval(pollingInterval);
        }

        pollingInterval = setInterval(async () => {
            try {
                const response = await fetch(`/tasks/${taskId}`);
                if (!response.ok) {
                    if (response.status === 404) {
                        throw new Error("タスクが見つかりません。");
                    }
                    throw new Error(`状態確認に失敗: ${response.status}`);
                }
                const task = await response.json();
                updateUIBasedOnTask(task);

            } catch (error) {
                console.error(`タスク[${taskId}]の状態取得中にエラーが発生:`, error);
                showStatus(`エラー: ${error.message}`, 'failure');
                stopPolling();
                setFormDisabled(false);
            }
        }, 3000); // 3秒間隔
    }

    /**
     * ポーリングを停止します。
     */
    function stopPolling() {
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
    }

    /**
     * タスクの状態に基づいてUIを更新します。
     * @param {object} task - 更新するタスクのオブジェクト
     */
    function updateUIBasedOnTask(task) {
        switch (task.status) {
            case 'SUCCESS':
                stopPolling();
                clearStatusAndLink();
                createDownloadLink(task);
                setFormDisabled(false);
                urlInput.value = '';
                break;
            case 'FAILURE':
                stopPolling();
                showStatus(`失敗しました: ${task.details || '不明なエラー'}`, 'failure');
                setFormDisabled(false);
                break;
            case 'PROCESSING':
            case 'STARTED':
            case 'PENDING':
                showStatus('処理中...', 'processing');
                break;
        }
    }

    /**
     * ダウンロードリンクと削除ボタンを作成して表示します。
     * @param {object} task - 成功したタスクオブジェクト
     */
    function createDownloadLink(task) {
        const filename = task.details?.original_filename || 'video.mp4';
        const downloadUrl = task.download_url;
        const taskId = task.task_id;

        // コンテナ要素を作成
        const container = document.createElement('div');
        container.className = 'download-action-container';

        // ダウンロードリンクを作成
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.textContent = `✅ ${filename} をダウンロード`;
        link.className = 'download-link';
        link.setAttribute('download', filename);

        // 削除ボタンを作成
        const deleteButton = document.createElement('button');
        deleteButton.textContent = 'サーバーから削除';
        deleteButton.className = 'delete-btn';

        // ★★★ 変更点 ★★★
        // 削除ボタンにクリックイベントを追加
        deleteButton.addEventListener('click', async () => {
            if (confirm('このファイルをサーバーから削除しますか？\n（ダウンロードが完了していることを確認してください）')) {
                await deleteTaskFromServer(taskId);
                // UIからコンテナ全体を削除
                container.remove();
                showStatus('ファイルはサーバーから削除されました。', 'processing');
            }
        });

        // 要素をコンテナに追加
        container.appendChild(link);
        container.appendChild(deleteButton);
        
        // コンテナをDOMに追加
        downloadLinkContainer.appendChild(container);
    }

    /**
     * サーバーからタスクとファイルを削除します。
     * @param {string} taskId - 削除するタスクID
     */
    async function deleteTaskFromServer(taskId) {
        try {
            const response = await fetch(`/tasks/${taskId}`, { method: 'DELETE' });
            if (!response.ok) {
                console.error('サーバーからのファイル削除に失敗しました。');
            }
            console.log(`Task ${taskId} deleted from server.`);
        } catch (error) {
            console.error('削除APIの呼び出し中にエラーが発生しました:', error);
        }
    }


    /**
     * ステータスメッセージを表示します。
     * @param {string} message - 表示するメッセージ
     * @param {'processing'|'failure'} type - メッセージの種類
     */
    function showStatus(message, type) {
        statusContainer.textContent = message;
        statusContainer.className = `status ${type}`;
        statusContainer.style.display = 'block';
    }

    /**
     * ステータスとダウンロードリンクの表示をクリアします。
     */
    function clearStatusAndLink() {
        statusContainer.style.display = 'none';
        statusContainer.textContent = '';
        downloadLinkContainer.innerHTML = '';
    }

    /**
     * フォームの有効/無効状態を設定します。
     * @param {boolean} disabled - trueで無効、falseで有効
     */
    function setFormDisabled(disabled) {
        urlInput.disabled = disabled;
        submitButton.disabled = disabled;
    }
});