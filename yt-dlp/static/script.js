document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('url-form');
    const urlInput = document.getElementById('video-url');
    const tasksList = document.getElementById('tasks-list');
    const pollingIntervals = new Map();

    async function loadInitialTasks() {
        try {
            const response = await fetch('/tasks/history');
            if (!response.ok) throw new Error('タスク履歴の取得に失敗しました。');
            const tasks = await response.json();
            tasksList.innerHTML = '';
            tasks.forEach(task => addTaskToList(task, false));
        } catch (error) {
            console.error(error);
        }
    }

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
                status: 'STARTED'
            }, true);
            urlInput.value = '';
        } catch (error) {
            console.error(error);
            alert(error.message);
        }
    });

    // 削除ボタンのクリック処理
    tasksList.addEventListener('click', async (e) => {
        if (e.target.classList.contains('delete-btn')) {
            const taskId = e.target.dataset.taskId;
            if (!taskId || !confirm('このタスクとファイルを本当に削除しますか？')) return;

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

    function addTaskToList(task, prepend = false) {
        const listItem = document.createElement('li');
        listItem.id = `task-${task.task_id}`;
        
        // 初期描画用のプレースホルダー。updateTaskStatusですぐに上書きされる。
        listItem.innerHTML = `<span class="url-placeholder"></span><span class="status"></span>`;
        
        if (prepend) tasksList.prepend(listItem);
        else tasksList.appendChild(listItem);

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
                if (!response.ok) {
                    console.error(`Status check for task [${taskId}] failed with status ${response.status}`);
                    return;
                };
                const data = await response.json();
                
                // ポーリングで取得したデータにはURLが含まれないため、DOMから引き継ぐ
                const listItem = document.getElementById(`task-${taskId}`);
                const urlElement = listItem?.querySelector('a.url');
                if (urlElement && !data.url) {
                    data.url = urlElement.href;
                }
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

        let isTaskFinished = false;
        const deleteButtonHtml = `<button class="delete-btn" data-task-id="${task.task_id}">削除</button>`;
        
        // URL情報をタスクオブジェクトまたは既存のDOM要素から取得
        const urlElement = listItem.querySelector('a.url');
        const originalUrl = task.url || (urlElement ? urlElement.href : '');

        // リンクを生成するヘルパー関数
        const createVideoLink = (text, url) => {
            if (url) {
                return `<a href="${url}" class="url" target="_blank" rel="noopener noreferrer" title="${url}">${text}</a>`;
            }
            return `<span class="url">${text}</span>`;
        };

        switch (task.status) {
            case 'SUCCESS':
                const filename = task.details.original_filename || 'video.mp4';
                listItem.innerHTML = `
                    ${createVideoLink(filename, originalUrl)}
                    <span class="status success">
                        <div class="actions">
                            <a href="${task.download_url}" class="download-link" download="${filename}">ダウンロード</a>
                            ${deleteButtonHtml}
                        </div>
                    </span>`;
                isTaskFinished = true;
                break;

            case 'FAILURE':
                listItem.innerHTML = `
                    ${createVideoLink(originalUrl || 'URL不明', originalUrl)}
                    <span class="status failure">
                        <div class="actions">
                            <span>失敗</span>
                            ${deleteButtonHtml}
                        </div>
                    </span>`;
                isTaskFinished = true;
                break;

            case 'PROCESSING':
            case 'STARTED':
                listItem.innerHTML = `
                    ${createVideoLink(originalUrl, originalUrl)}
                    <span class="status processing">処理中...</span>`;
                break;

            default: // PENDING やその他の未知のステータス
                listItem.innerHTML = `
                    ${createVideoLink(originalUrl || 'URL不明', originalUrl)}
                    <span class="status">待機中...</span>`;
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
