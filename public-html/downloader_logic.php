<?php
// downloader_logic.php

// 表示用の変数を初期化
$download_link = "";
$error_message = "";

// フォームが送信された場合に処理を実行
if ($_SERVER["REQUEST_METHOD"] == "POST" && !empty($_POST['video_url'])) {

    // フォームからURLを取得
    $video_url = $_POST['video_url'];

    // セキュリティのためURLをエスケープ
    $safe_url = escapeshellarg($video_url);

    // 実行するコマンドを定義
    $command = "/usr/local/bin/yt-dlp -f bestvideo[vcodec*=avc1]+bestaudio[acodec*=mp4a] --embed-thumbnail --print filename -o 'downloads/%(title)s.%(ext)s' " . $safe_url . " 2>&1";
    
    // コマンドを実行し、出力を取得
    $output = shell_exec($command);
}
?>