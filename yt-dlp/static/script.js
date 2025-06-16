document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('url-form');
    const urlInput = document.getElementById('video-url');
    const tasksList = document.getElementById('tasks-list');
    const pollingIntervals = new Map();

    // ページ読み込み時に過去のタスクを読み込む
    async function loadInitialTasks() {
        try {
            const response = await fetch('/tasks/history');
            if (!response.ok) {
                throw new Error('タスク履歴の取得に失敗しました。');
            }
            const tasks = await response.json();
            tasksList.innerHTML = ''; // 一旦リストをクリア
            for (const task of tasks) {
                addTaskToList(task, false); // リストの末尾に追加
            }
        } catch (error) {
            console.error(error);
        }
    }

    // フォーム送信時の処理
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
                status: 'PENDING'
            }, true); // 新しいタスクはリストの先頭に追加

            urlInput.value = '';
        } catch (error) {
            console.error(error);
            alert(error.message);
        }
    });

    function addTaskToList(task, prepend = false) {
        const listItem = document.createElement('li');
        listItem.id = `task-${task.task_id}`;
        
        const urlHtml = task.url ? `<span class="url">${task.url}</span>` : '';
        listItem.innerHTML = `${urlHtml}<span class="status"></span>`;
        
        if (prepend) {
            tasksList.prepend(listItem);
        } else {
            tasksList.appendChild(listItem);
        }

        updateTaskStatus(task);
        
        if (task.status !== 'SUCCESS' && task.status !== 'FAILURE') {
            startPolling(task.task_id);
        }
    }

    function startPolling(taskId) {
        if (pollingIntervals.has(taskId)) return;

        const intervalId = setInterval(async () => {
            try {
                const response = await fetch(`/tasks/${taskId}`);
                const data = await response.json();
                updateTaskStatus(data);
            } catch (error) {
                console.error(`タスク[${taskId}]の状態取得に失敗:`, error);
            }
        }, 3000);

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
                
                // URLを表示していた要素を探して、内容をファイル名に置き換える
                const infoElement = listItem.querySelector('.url');
                if (infoElement) {
                    infoElement.textContent = filename;
                }

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
            default: // PENDING
                statusElement.className = 'status';
                statusElement.textContent = '待機中...';
                break;
        }

        if (isTaskFinished) {
            const intervalId = pollingIntervals.get(task.task_id);
            if (intervalId) {
                clearInterval(intervalId);
                pollingIntervals.delete(task.task_id);
            }
        }
    }
    
    loadInitialTasks();
});
