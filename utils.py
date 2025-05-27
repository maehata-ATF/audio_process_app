from datetime import datetime
from pathlib import Path

import streamlit as st

from config import OUTPUT_DIR


def save_markdown_file(content, filename_prefix, description=""):
    """
    マークダウンファイルを保存する

    Args:
        content (str): 保存するコンテンツ
        filename_prefix (str): ファイル名の接頭辞
        description (str): ファイルの説明

    Returns:
        str: 保存されたファイルのパス
    """
    if not content:
        return None

    # タイムスタンプ付きファイル名を生成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.md"
    filepath = OUTPUT_DIR / filename

    try:
        # ディレクトリが存在しない場合は作成
        OUTPUT_DIR.mkdir(exist_ok=True)

        # ファイルに書き込み
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return str(filepath)

    except Exception as e:
        st.error(f"ファイル保存に失敗しました: {e}")
        return None


def create_download_button(content, filename, label, description=""):
    """
    ダウンロードボタンを作成する

    Args:
        content (str): ダウンロードするコンテンツ
        filename (str): ダウンロード時のファイル名
        label (str): ボタンのラベル
        description (str): ファイルの説明
    """
    if content:
        st.download_button(
            label=label,
            data=content,
            file_name=filename,
            mime="text/markdown",
            help=description
        )


def display_processing_status(step, total_steps, message):
    """
    処理状況を表示する

    Args:
        step (int): 現在のステップ
        total_steps (int): 総ステップ数
        message (str): 表示するメッセージ
    """
    progress = step / total_steps
    st.progress(progress)
    st.info(f"ステップ {step}/{total_steps}: {message}")


def format_file_size(size_bytes):
    """
    ファイルサイズを読みやすい形式にフォーマット

    Args:
        size_bytes (int): バイト単位のファイルサイズ

    Returns:
        str: フォーマットされたファイルサイズ
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB"]
    size = size_bytes
    i = 0

    while size >= 1024 and i < len(size_names) - 1:
        size /= 1024
        i += 1

    return f"{size:.1f} {size_names[i]}"


def validate_api_key():
    """
    OpenAI APIキーが設定されているかチェック

    Returns:
        bool: APIキーが設定されているかどうか
    """
    from config import OPENAI_API_KEY

    if not OPENAI_API_KEY:
        st.error("⚠️ OpenAI APIキーが設定されていません")
        st.markdown("""
        以下の手順でAPIキーを設定してください：
        
        1. [OpenAI API](https://platform.openai.com/api-keys)でAPIキーを取得
        2. 環境変数 `OPENAI_API_KEY` を設定
        3. アプリケーションを再起動
        
        **設定例：**
        ```bash
        export OPENAI_API_KEY="your-api-key-here"
        ```
        
        または `.env` ファイルを作成：
        ```
        OPENAI_API_KEY=your-api-key-here
        ```
        """)
        return False

    return True


def show_success_message(saved_files):
    """
    処理完了メッセージを表示

    Args:
        saved_files (list): 保存されたファイルのパスリスト
    """
    st.success("✅ 処理が完了しました！")

    if saved_files:
        st.info("📁 以下のファイルが保存されました：")
        for file_path in saved_files:
            if file_path:
                st.write(f"- `{file_path}`")


def clear_upload_cache():
    """
    アップロード関連のキャッシュをクリア
    """
    # Streamlitのキャッシュをクリア
    if 'uploaded_audio' in st.session_state:
        del st.session_state.uploaded_audio
    if 'transcript' in st.session_state:
        del st.session_state.transcript
