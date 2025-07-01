document.addEventListener('DOMContentLoaded', () => {
    const urlInput = document.getElementById('video-url');
    const videoButton = document.getElementById('download-video-btn');
    const audioButton = document.getElementById('download-audio-btn');
    const statusContainer = document.getElementById('status-container');
    const downloadLinkContainer = document.getElementById('download-link-container');
    const statusMessageEl = document.getElementById('status-message');
    const taskIdDisplayEl = document.getElementById('task-id-display');

    let pollingInterval = null;

    /**
     * タスク作成リクエストを送信する共通関数
     * @param {boolean} isAudioOnly - 音声のみの場合はtrue
     */
    const createTask = async (isAudioOnly) => {
        const url = urlInput.value;
        if (!url) {
            alert('URLを入力してください。');
            return;
        }

        // 以前の表示をクリアし、フォームを無効化
        clearStatusAndLink();
        setFormDisabled(true);

        try {
            const response = await fetch('/tasks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, audio_only: isAudioOnly }),
            });
            if (!response.ok) throw new Error('タスクの作成に失敗しました。');
            const data = await response.json();
            showStatus('処理中...', 'processing', data.task_id);
            startPolling(data.task_id);
        } catch (error) {
            console.error(error);
            showStatus(`エラー: ${error.message}`, 'failure');
            setFormDisabled(false);
        }
    };

    // [変更] 動画・音声ボタンのクリックイベントリスナー
    videoButton.addEventListener('click', () => createTask(false));
    audioButton.addEventListener('click', () => createTask(true));


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
                showStatus(`失敗しました: ${task.details || '不明なエラー'}`, 'failure', task.task_id);
                setFormDisabled(false);
                break;
            case 'PROCESSING':
            case 'STARTED':
            case 'PENDING':
                showStatus('処理中...', 'processing', task.task_id);
                break;
        }
    }

    /**
     * ダウンロードリンクと削除ボタンを作成して表示します。
     * @param {object} task - 成功したタスクオブジェクト
     */
    function createDownloadLink(task) {
        const filename = task.details?.original_filename || 'download';
        const downloadUrl = task.download_url;
        const taskId = task.task_id;

        const container = document.createElement('div');
        container.className = 'download-action-container';

        const link = document.createElement('a');
        link.href = downloadUrl;
        link.textContent = `✅ ${filename} をダウンロード`;
        link.className = 'download-link';
        link.setAttribute('download', filename);

        const deleteButton = document.createElement('button');
        deleteButton.textContent = '🗑️ 削除';
        deleteButton.className = 'delete-btn';

        deleteButton.addEventListener('click', async () => {
            // [修正] confirmは使わない
            const userConfirmed = window.confirm('このファイルをサーバーから削除しますか？\n（ダウンロードが完了していることを確認してください）');
            if (userConfirmed) {
                await deleteTaskFromServer(taskId);
                container.remove();
                showStatus('ファイルはサーバーから削除されました。', 'processing');
            }
        });

        container.appendChild(link);
        container.appendChild(deleteButton);
        
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
     * @param {string|null} taskId - 表示するタスクID (オプション)
     */
    function showStatus(message, type, taskId = null) {
        statusContainer.style.display = 'flex';
        statusContainer.className = `status ${type}`;
        statusMessageEl.textContent = message;
        
        if (taskId) {
            taskIdDisplayEl.textContent = `Task ID: ${taskId}`;
        } else {
            taskIdDisplayEl.textContent = '';
        }
    }

    /**
     * ステータスとダウンロードリンクの表示をクリアします。
     */
    function clearStatusAndLink() {
        statusContainer.style.display = 'none';
        statusMessageEl.textContent = '';
        taskIdDisplayEl.textContent = '';
        downloadLinkContainer.innerHTML = '';
    }

    /**
     * フォームの有効/無効状態を設定します。
     * @param {boolean} disabled - trueで無効、falseで有効
     */
    function setFormDisabled(disabled) {
        urlInput.disabled = disabled;
        videoButton.disabled = disabled;
        audioButton.disabled = disabled;
    }
});
