document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('url-form');
    const urlInput = document.getElementById('video-url');
    const tasksList = document.getElementById('tasks-list');

    // タスクのポーリング間隔を管理するためのオブジェクト
    const pollingIntervals = new Map();

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = urlInput.value;
        if (!url) return;

        try {
            // 1. バックエンドにタスク作成をリクエスト
            const response = await fetch('/tasks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });

            if (!response.ok) {
                throw new Error('タスクの作成に失敗しました。');
            }

            const data = await response.json();
            const { task_id } = data;

            // 2. UIに新しいタスクを追加
            const listItem = document.createElement('li');
            listItem.id = `task-${task_id}`;
            listItem.innerHTML = `
                <span class="url">${url}</span>
                <span class="status processing">処理中...</span>
            `;
            tasksList.prepend(listItem);

            // 3. このタスクの状態を定期的に確認開始
            startPolling(task_id);
            
            urlInput.value = '';

        } catch (error) {
            console.error(error);
            alert(error.message);
        }
    });

    function startPolling(taskId) {
        const intervalId = setInterval(async () => {
            try {
                const response = await fetch(`/tasks/${taskId}`);
                const data = await response.json();
                updateTaskStatus(data);
            } catch (error) {
                console.error(`タスク[${taskId}]の状態取得に失敗:`, error);
                // エラーが続くとポーリングを止めるなどの処理も可能
            }
        }, 3000); // 3秒ごとに状態を確認

        pollingIntervals.set(taskId, intervalId);
    }

    function updateTaskStatus(task) {
        const listItem = document.getElementById(`task-${task.task_id}`);
        if (!listItem) return;

        const statusElement = listItem.querySelector('.status');
        let isTaskFinished = false;

        switch (task.status) {
            case 'SUCCESS':
                const downloadUrl = task.download_url;
                const filename = task.details.original_filename || 'video.mp4';
                statusElement.className = 'status success';
                statusElement.innerHTML = `<a href="${downloadUrl}" class="download-link" download="${filename}">ダウンロード</a>`;
                isTaskFinished = true;
                break;
            case 'FAILURE':
                statusElement.className = 'status failure';
                statusElement.textContent = '失敗';
                isTaskFinished = true;
                break;
            case 'PROCESSING':
            case 'STARTED':
                statusElement.className = 'status processing';
                statusElement.textContent = '処理中...';
                break;
            default:
                statusElement.textContent = '待機中...';
                break;
        }

        // タスクが完了または失敗したら、ポーリングを停止
        if (isTaskFinished) {
            const intervalId = pollingIntervals.get(task.task_id);
            if (intervalId) {
                clearInterval(intervalId);
                pollingIntervals.delete(task.task_id);
            }
        }
    }
});
