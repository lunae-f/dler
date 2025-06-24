document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('url-form');
    const urlInput = document.getElementById('video-url');
    const tasksList = document.getElementById('tasks-list');
    const pollingIntervals = new Map();

    /**
     * 初期表示時にタスク履歴をサーバーから読み込みます。
     */
    async function loadInitialTasks() {
        try {
            const response = await fetch('/tasks/history');
            if (!response.ok) throw new Error('タスク履歴の取得に失敗しました。');
            const tasks = await response.json();
            tasksList.innerHTML = ''; // リストをクリア
            tasks.forEach(task => addTaskToList(task, false));
        } catch (error) {
            console.error(error);
        }
    }

    /**
     * フォームの送信イベントを処理します。
     */
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = urlInput.value;
        if (!url) return;

        try {
            const response = await fetch('/tasks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });
            if (!response.ok) throw new Error('タスクの作成に失敗しました。');
            const data = await response.json();
            addTaskToList({
                task_id: data.task_id,
                url: data.url,
                status: 'STARTED' // 初期ステータス
            }, true);
            urlInput.value = '';
        } catch (error) {
            console.error(error);
            // 本番環境ではよりユーザーフレンドリーなエラー表示が望ましい
            alert(error.message);
        }
    });

    /**
     * タスクリスト内のクリックイベントを処理します（削除ボタン）。
     */
    tasksList.addEventListener('click', async (e) => {
        if (e.target.classList.contains('delete-btn')) {
            const taskId = e.target.dataset.taskId;
            // confirm は一時的な措置。より良いUI/UXのためにはカスタムモーダルが望ましい。
            if (!taskId || !confirm('このタスクと関連ファイルを本当に削除しますか？')) return;

            try {
                const response = await fetch(`/tasks/${taskId}`, { method: 'DELETE' });
                if (!response.ok) throw new Error('削除に失敗しました。');
                document.getElementById(`task-${taskId}`)?.remove();
            } catch (error) {
                console.error(error);
                alert(error.message);
            }
        }
    });

    /**
     * タスクをリストに追加します。
     * @param {object} task - タスクオブジェクト
     * @param {boolean} prepend - trueの場合、リストの先頭に追加します
     */
    function addTaskToList(task, prepend = false) {
        // 既存のタスクがリストになければ追加
        if (document.getElementById(`task-${task.task_id}`)) return;

        const listItem = document.createElement('li');
        listItem.id = `task-${task.task_id}`;
        
        if (prepend) {
            tasksList.prepend(listItem);
        } else {
            tasksList.appendChild(listItem);
        }

        updateTaskListItem(task); // リストアイテムの中身を更新
        
        // 完了または失敗していないタスクはポーリングを開始
        if (task.status !== 'SUCCESS' && task.status !== 'FAILURE') {
            startPolling(task.task_id);
        }
    }

    /**
     * 指定されたタスクIDのポーリングを開始します。
     * @param {string} taskId - タスクID
     */
    function startPolling(taskId) {
        if (pollingIntervals.has(taskId)) return;

        const intervalId = setInterval(async () => {
            try {
                const response = await fetch(`/tasks/${taskId}`);
                if (!response.ok) {
                    console.error(`タスク[${taskId}]の状態確認に失敗: ${response.status}`);
                    // 404などの場合はポーリングを停止することも検討
                    return;
                };
                const data = await response.json();
                updateTaskListItem(data);
            } catch (error) {
                console.error(`タスク[${taskId}]の状態取得中にエラーが発生:`, error);
                // エラーが続く場合はポーリングを停止するロジックを追加することも可能
            }
        }, 3000); // 3秒間隔

        pollingIntervals.set(taskId, intervalId);
    }

    /**
     * タスクの状態に基づいてリストアイテムの表示を安全に更新します。
     * XSS脆弱性を防ぐため、innerHTMLではなくDOM操作APIを使用します。
     * @param {object} task - 更新するタスクのオブジェクト
     */
    function updateTaskListItem(task) {
        const listItem = document.getElementById(`task-${task.task_id}`);
        if (!listItem) return;

        // --- 安全なDOM更新 ---
        // 1. 中身を一旦空にする
        listItem.innerHTML = '';

        // 2. 左側のコンテンツ要素（URLまたはファイル名）を作成
        const contentEl = document.createElement('a');
        contentEl.className = 'url';
        const originalUrl = task.url || '#';
        if (originalUrl !== '#') {
            contentEl.href = originalUrl;
            contentEl.target = '_blank';
            contentEl.rel = 'noopener noreferrer';
            contentEl.title = originalUrl;
        }

        // 3. 右側のステータス・アクション要素を作成
        const statusEl = document.createElement('span');
        const actionsContainer = document.createElement('div');
        actionsContainer.className = 'actions';
        
        let isTaskFinished = false;

        // 4. タスクの状態に応じて各要素の内容を決定
        switch (task.status) {
            case 'SUCCESS':
                isTaskFinished = true;
                statusEl.className = 'status success';
                const filename = task.details?.original_filename || 'video.mp4';
                // textContent を使って安全にテキストを設定
                contentEl.textContent = filename;

                const downloadLink = document.createElement('a');
                downloadLink.className = 'download-link';
                downloadLink.href = task.download_url;
                downloadLink.textContent = 'ダウンロード';
                // download属性にファイル名を指定
                downloadLink.setAttribute('download', filename);

                actionsContainer.appendChild(downloadLink);
                actionsContainer.appendChild(createDeleteButton(task.task_id));
                statusEl.appendChild(actionsContainer);
                break;

            case 'FAILURE':
                isTaskFinished = true;
                statusEl.className = 'status failure';
                contentEl.textContent = originalUrl;

                const failureText = document.createElement('span');
                failureText.textContent = '失敗';
                
                actionsContainer.appendChild(failureText);
                actionsContainer.appendChild(createDeleteButton(task.task_id));
                statusEl.appendChild(actionsContainer);
                break;

            case 'PROCESSING':
            case 'STARTED':
                statusEl.className = 'status processing';
                statusEl.textContent = '処理中...';
                contentEl.textContent = originalUrl;
                break;

            default: // PENDING やその他の未知のステータス
                statusEl.className = 'status';
                statusEl.textContent = '待機中...';
                contentEl.textContent = originalUrl;
                break;
        }
        
        // 5. 作成した要素をリストアイテムに追加
        listItem.appendChild(contentEl);
        listItem.appendChild(statusEl);

        // 6. タスクが完了または失敗した場合、ポーリングを停止
        if (isTaskFinished) {
            const intervalId = pollingIntervals.get(task.task_id);
            if (intervalId) {
                clearInterval(intervalId);
                pollingIntervals.delete(task.task_id);
            }
        }
    }
    
    /**
     * 削除ボタンのHTML要素を生成します。
     * @param {string} taskId - 削除対象のタスクID
     * @returns {HTMLButtonElement} 削除ボタン要素
     */
    function createDeleteButton(taskId) {
        const button = document.createElement('button');
        button.className = 'delete-btn';
        button.dataset.taskId = taskId;
        button.textContent = '削除';
        return button;
    }

    // 初期化
    loadInitialTasks();
});
