<?php
// downloader_logic.php

// フォームが送信された場合に処理を実行
if ($_SERVER["REQUEST_METHOD"] == "POST" && !empty($_POST['video_url'])) {

    // フォームからURLを取得
    $video_url = $_POST['video_url'];

    // セキュリティのためURLをエスケープ
    $safe_url = escapeshellarg($video_url);

    // 実行するコマンドを定義
    $command = "/usr/local/bin/yt-dlp -f bestvideo[vcodec*=avc1]+bestaudio[acodec*=mp4a] --embed-thumbnail -o 'downloads/%(title)s.%(ext)s' " . $safe_url;
    
    // コマンドを実行し、出力を取得
    $output = shell_exec($command);
}
?>