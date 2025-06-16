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
        
        const urlHtml = task.url ? `<span class="url">${task.url}</span>` : '';
        listItem.innerHTML = `${urlHtml}<span class="status"></span>`;
        
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
                if (!response.ok) throw new Error('Status check failed');
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

        const deleteButtonHtml = `<button class="delete-btn" data-task-id="${task.task_id}">削除</button>`;

        switch (task.status) {
            case 'SUCCESS':
                const downloadUrl = task.download_url;
                const filename = task.details.original_filename || 'video.mp4';
                statusElement.className = 'status success';
                statusElement.innerHTML = `<div class="actions"><a href="${downloadUrl}" class="download-link" download="${filename}">ダウンロード</a>${deleteButtonHtml}</div>`;
                
                const infoElement = listItem.querySelector('.url');
                if (infoElement) infoElement.textContent = filename;
                isTaskFinished = true;
                break;
            case 'FAILURE':
                statusElement.className = 'status failure';
                statusElement.innerHTML = `<div class="actions"><span>失敗</span>${deleteButtonHtml}</div>`;
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
