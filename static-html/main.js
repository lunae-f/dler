// JavaScriptのロジックは前回とほぼ同じため、変数名のみ新しいIDに合わせて調整
const form = document.getElementById('download-form');
const videoUrlInput = document.getElementById('video-url');
const submitButton = document.getElementById('submit-button');

const statusContainer = document.getElementById('status-container');
const loader = document.getElementById('loader');
const resultDiv = document.getElementById('result');

const successMessage = document.getElementById('success-message');
const errorMessage = document.getElementById('error-message');
const errorText = document.getElementById('error-text');

const downloadLink = document.getElementById('download-link');
const downloadTitle = document.getElementById('download-title');

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    // UIをリセットしてローディング状態へ
    submitButton.disabled = true;
    statusContainer.style.display = 'block';
    loader.style.display = 'flex';
    resultDiv.classList.add('hidden');
    successMessage.classList.add('hidden');
    errorMessage.classList.add('hidden');
    
    const url = videoUrlInput.value;

    try {
        const response = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url }),
        });

        const data = await response.json();
        
        loader.style.display = 'none';
        resultDiv.classList.remove('hidden');

        if (response.ok) {
            successMessage.classList.remove('hidden');
            downloadLink.href = data.download_url;
            downloadLink.setAttribute('download', data.title);
            downloadTitle.textContent = `「${data.title || 'ファイル'}」を保存`;
        } else {
            errorMessage.classList.remove('hidden');
            errorText.textContent = data.error || '不明なエラーが発生しました。';
        }

    } catch (error) {
        loader.style.display = 'none';
        resultDiv.classList.remove('hidden');
        errorMessage.classList.remove('hidden');
        errorText.textContent = 'サーバーとの通信に失敗しました。';
    } finally {
        submitButton.disabled = false;
    }
});