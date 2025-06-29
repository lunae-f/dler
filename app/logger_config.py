# yt-dlp/logger_config.py
import logging
import sys

def setup_logger():
    """
    アプリケーション用の構造化ロガーをセットアップします。

    ログはコンソールに標準出力され、タイムスタンプ、ロガー名、
    ログレベル、メッセージを含む一貫したフォーマットで表示されます。
    """
    # ルートロガーを取得
    logger = logging.getLogger()
    
    # ログレベルを設定 (INFOレベル以上のログを記録)
    logger.setLevel(logging.INFO)

    # ハンドラが既に設定されている場合、重複して追加しないようにする
    if not logger.handlers:
        # ログをコンソールに出力するためのハンドラを作成
        handler = logging.StreamHandler(sys.stdout)
        
        # ログメッセージのフォーマットを定義
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        
        # ハンドラをロガーに追加
        logger.addHandler(handler)

    return logger

# ロガーインスタンスを初期化してエクスポート
logger = setup_logger()
