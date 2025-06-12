const form = document.getElementById(\'download-form\');
const videoUrlInput = document.getElementById(\'video-url\');
const submitButton = document.getElementById(\'submit-button\');

const statusContainer = document.getElementById(\'status-container\');
const loader = document.getElementById(\'loader\');
const resultDiv = document.getElementById(\'result\');

const successMessage = document.getElementById(\'success-message\');
const errorMessage = document.getElementById(\'error-message\');
const errorText = document.getElementById(\'error-text\');

const downloadLink = document.getElementById(\'download-link\');
const downloadTitle = document.getElementById(\'download-title\');

const progressText = document.createElement(\'p\');
progressText.id = \'progress-text\';
progressText.className = \'text-sm text-gray-400 mt-1\';
loader.appendChild(progressText);

let pollingInterval;

const API_BASE_URL = 'https://5000-igiwe1dwmmkhc2g5k46xr-33eec26f.manusvm.computer';

form.addEventListener(\'submit\', async (e) => {
    e.preventDefault();

    // UIをリセットしてローディング状態へ
    submitButton.disabled = true;
    statusContainer.style.display = \'block\';
    loader.style.display = \'flex\';
    resultDiv.classList.add(\'hidden\');
    successMessage.classList.add(\'hidden\');
    errorMessage.classList.add(\'hidden\');
    progressText.textContent = \'キューに追加されました。\';

    const url = videoUrlInput.value;

    try {
        const response = await fetch(`${API_BASE_URL}/api/download`, {
            method: \'POST\',
            headers: { \'Content-Type\': \'application/json\' },
            body: JSON.stringify({ url: url }),
        });

        const data = await response.json();

        if (response.ok && data.job_id) {
            const job_id = data.job_id;
            pollingInterval = setInterval(async () => {
                const statusResponse = await fetch(`${API_BASE_URL}/api/status/${job_id}`);
                const statusData = await statusResponse.json();

                if (statusResponse.ok) {
                    progressText.textContent = statusData.progress || \'処理中...\';
                    if (statusData.status === \'completed\') {
                        clearInterval(pollingInterval);
                        loader.style.display = \'none\';
                        resultDiv.classList.remove(\'hidden\');
                        successMessage.classList.remove(\'hidden\');
                        downloadLink.href = statusData.download_url;
                        downloadLink.setAttribute(\'download\', statusData.title);
                        downloadTitle.textContent = `「${statusData.title || \'ファイル\'}」を保存`;
                        if (statusData.is_playlist) {
                            downloadTitle.textContent += \' (プレイリストの最初の動画)\';
                        }
                    } else if (statusData.status === \'failed\') {
                        clearInterval(pollingInterval);
                        loader.style.display = \'none\';
                        resultDiv.classList.remove(\'hidden\');
                        errorMessage.classList.remove(\'hidden\');
                        errorText.textContent = statusData.error || \'不明なエラーが発生しました。\';
                    }
                } else {
                    clearInterval(pollingInterval);
                    loader.style.display = \'none\';
                    resultDiv.classList.remove(\'hidden\');
                    errorMessage.classList.remove(\'hidden\');
                    errorText.textContent = statusData.error || \'ステータスの取得に失敗しました。\';
                }
            }, 2000); // 2秒ごとにポーリング

        } else {
            loader.style.display = \'none\';
            resultDiv.classList.remove(\'hidden\');
            errorMessage.classList.remove(\'hidden\');
            errorText.textContent = data.error || \'不明なエラーが発生しました。\';
        }

    } catch (error) {
        clearInterval(pollingInterval);
        loader.style.display = \'none\';
        resultDiv.classList.remove(\'hidden\');
        errorMessage.classList.remove(\'hidden\');
        errorText.textContent = \'サーバーとの通信に失敗しました。\';
    } finally {
        submitButton.disabled = false;
    }
});


