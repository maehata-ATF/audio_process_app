from datetime import datetime
from pathlib import Path

import streamlit as st

from audio_processor import AudioProcessor
from config import (AVAILABLE_MODELS, GPT_MODEL, check_system_requirements,
                    get_logger)
from text_processor import TextProcessor
from utils import (create_download_button, display_processing_status,
                   save_markdown_file, show_success_message, validate_api_key)

# ページ設定
st.set_page_config(
    page_title="音声処理アプリケーション",
    page_icon="🎤",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ロガーの初期化
logger = get_logger(__name__)


@st.cache_resource
def get_audio_processor():
    """AudioProcessorのインスタンスを取得（キャッシュ付き）"""
    logger.info("AudioProcessorキャッシュから取得/作成")
    return AudioProcessor()


@st.cache_resource
def get_text_processor():
    """TextProcessorのインスタンスを取得（キャッシュ付き）"""
    logger.info("TextProcessorキャッシュから取得/作成")
    return TextProcessor()


def display_chat_history():
    """チャット履歴を表示"""
    if 'chat_messages' not in st.session_state:
        st.session_state.chat_messages = []

    # チャット履歴表示エリア
    chat_container = st.container()

    with chat_container:
        if st.session_state.chat_messages:
            st.markdown("### 💬 チャット履歴")

            for i, message in enumerate(st.session_state.chat_messages):
                timestamp = message.get('timestamp', datetime.now())
                role = message.get('role', 'user')
                content = message.get('content', '')

                # タイムスタンプ表示
                st.caption(f"{timestamp.strftime('%H:%M:%S')} - {role}")

                # メッセージ内容表示
                if role == 'user':
                    st.markdown(f"**👤 ユーザー:** {content}")
                else:
                    st.markdown(f"**🤖 アシスタント:** {content}")

                st.divider()
        else:
            st.info("💡 分析完了後、こちらでチャットができます。")


def add_chat_message(role: str, content: str):
    """チャットメッセージを追加"""
    if 'chat_messages' not in st.session_state:
        st.session_state.chat_messages = []

    message = {
        'role': role,
        'content': content,
        'timestamp': datetime.now()
    }

    st.session_state.chat_messages.append(message)


def clear_chat_history():
    """チャット履歴をクリア"""
    if 'chat_messages' in st.session_state:
        st.session_state.chat_messages = []

    # TextProcessorの履歴もクリア
    text_processor = get_text_processor()
    text_processor.clear_chat_history()


def display_token_info(text_processor: TextProcessor, model: str):
    """トークン情報を表示"""
    if hasattr(text_processor, 'chat_history'):
        history_summary = text_processor.get_chat_history_summary()

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("メッセージ数", history_summary['message_count'])

        with col2:
            st.metric("使用トークン数", history_summary['total_tokens'])

        with col3:
            from config import CONTEXT_LIMIT_PERCENTAGE, MODEL_TOKEN_LIMITS
            max_tokens = MODEL_TOKEN_LIMITS.get(model, 4096)
            limit_tokens = int(max_tokens * CONTEXT_LIMIT_PERCENTAGE)
            usage_percentage = (
                history_summary['total_tokens'] / limit_tokens * 100) if limit_tokens > 0 else 0
            st.metric("使用率", f"{usage_percentage:.1f}%")


def chat_interface(context_data: dict, model: str):
    """チャットインターフェース"""
    st.markdown("### 💬 AIチャット")
    st.markdown("分析結果について質問してください。ChatGPTのように会話履歴が保持されます。")

    # TextProcessorを取得
    text_processor = get_text_processor()

    # トークン情報表示
    with st.expander("📊 トークン使用状況", expanded=False):
        display_token_info(text_processor, model)

    # チャット履歴表示
    display_chat_history()

    # チャット入力フィールドのリセット用カウンター
    if 'chat_input_counter' not in st.session_state:
        st.session_state.chat_input_counter = 0

    # チャット入力
    col1, col2 = st.columns([4, 1])

    with col1:
        user_input = st.text_input(
            label="質問を入力してください:",
            placeholder="例: この会議の最も重要な決定事項は何ですか？",
            key=f"chat_input_{st.session_state.chat_input_counter}"
        )

    with col2:
        send_button = st.button("送信", type="primary")
        clear_button = st.button("履歴クリア")

    if clear_button:
        clear_chat_history()
        st.rerun()

    if send_button and user_input:
        try:
            # ユーザーメッセージを履歴に追加
            add_chat_message("user", user_input)

            # AIの回答を取得
            with st.spinner("回答を生成中..."):
                response = text_processor.chat_with_context(
                    user_message=user_input,
                    context_data=context_data,
                    model=model
                )

            # AIの回答を履歴に追加
            add_chat_message("assistant", response)

            # 入力フィールドをリセットするためにカウンターを増加
            st.session_state.chat_input_counter += 1

            st.rerun()

        except Exception as e:
            st.error(f"チャット処理でエラーが発生しました: {e}")
            logger.error(f"チャット処理エラー: {e}", exc_info=True)


def meeting_summary_page():
    """議事録要約ページ"""
    logger.info("議事録要約ページ開始")

    # モード名を最上部に表示
    st.markdown("# 📝 議事録要約モード")

    # APIキーの確認
    if not validate_api_key():
        return

    # システム要件チェック
    requirements_met, issues = check_system_requirements()
    if not requirements_met:
        st.error("⚠️ システム要件が満たされていません:")
        for issue in issues:
            st.write(f"- {issue}")
        return

    # サイドバーでモデル選択
    with st.sidebar:
        st.markdown("### ⚙️ 設定")
        selected_model = st.selectbox(
            "GPTモデルを選択:",
            AVAILABLE_MODELS,
            index=AVAILABLE_MODELS.index(
                GPT_MODEL) if GPT_MODEL in AVAILABLE_MODELS else 0,
            help="高性能モデルほど精度が高いですが、費用も高くなります"
        )

    # ファイルアップロード
    st.markdown("### 📁 音声ファイルアップロード")
    uploaded_file = st.file_uploader(
        "音声ファイルを選択してください",
        type=['mp3', 'wav', 'm4a', 'flac', 'ogg'],
        help="対応形式: MP3, WAV, M4A, FLAC, OGG（最大200MB）"
    )

    if uploaded_file is not None:
        logger.info(f"ファイルアップロード: {uploaded_file.name}")

        # ファイル情報表示
        st.info(f"📄 ファイル名: {uploaded_file.name}")
        st.info(f"📊 ファイルサイズ: {uploaded_file.size / 1024 / 1024:.2f} MB")

        # 処理開始ボタン
        if st.button("🚀 議事録要約を開始", type="primary"):
            logger.info("議事録要約処理開始")

            try:
                # プロセッサーの取得
                audio_processor = get_audio_processor()
                text_processor = get_text_processor()

                # ステップ1: 文字起こし
                display_processing_status(1, 3, "音声ファイルを文字起こし中...")
                transcript = audio_processor.transcribe_audio(uploaded_file)

                if transcript is None:
                    st.error("❌ 文字起こしに失敗しました")
                    return

                # ステップ2: 文字起こしブラッシュアップ
                display_processing_status(2, 3, "文字起こしを整形中...")
                brushed_transcript = text_processor.brushup_transcript(
                    transcript, selected_model)

                # ステップ3: 議事録要約生成
                display_processing_status(3, 3, "議事録要約を生成中...")
                summary = text_processor.generate_meeting_summary(
                    brushed_transcript, selected_model)

                logger.info("議事録要約処理完了")

                # 結果をセッション状態に保存
                st.session_state.analysis_completed = True
                st.session_state.transcript = transcript
                st.session_state.brushed_transcript = brushed_transcript
                st.session_state.summary = summary
                st.session_state.selected_model = selected_model

                st.success("✅ 処理が完了しました！")
                st.rerun()

            except Exception as e:
                st.error(f"❌ 処理中にエラーが発生しました: {e}")
                logger.error(f"議事録要約処理エラー: {e}", exc_info=True)

    # 結果表示
    if st.session_state.get('analysis_completed', False):
        st.markdown("---")
        st.markdown("## 📋 処理結果")

        # タブで結果を表示
        tab1, tab2, tab3, tab4 = st.tabs(
            ["📄 元の文字起こし", "✨ 整形済み文字起こし", "📊 議事録要約", "💬 AIチャット"])

        with tab1:
            st.markdown("### 📄 元の文字起こし結果")
            st.text_area(
                label="元の文字起こし内容",
                value=st.session_state.transcript,
                height=300,
                disabled=True,
                label_visibility="collapsed"
            )
            create_download_button(
                st.session_state.transcript,
                f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                "📥 文字起こしをダウンロード"
            )

        with tab2:
            st.markdown("### ✨ 整形済み文字起こし結果")
            st.text_area(
                label="整形済み文字起こし内容",
                value=st.session_state.brushed_transcript,
                height=300,
                disabled=True,
                label_visibility="collapsed"
            )
            create_download_button(
                st.session_state.brushed_transcript,
                f"brushed_transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                "📥 整形済み文字起こしをダウンロード"
            )

        with tab3:
            st.markdown("### 📊 議事録要約")
            st.markdown(st.session_state.summary)
            create_download_button(
                st.session_state.summary,
                f"meeting_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                "📥 議事録要約をダウンロード"
            )

        with tab4:
            # チャットインターフェース
            context_data = {
                'transcript': st.session_state.transcript,
                'brushed_transcript': st.session_state.brushed_transcript,
                'summary': st.session_state.summary
            }
            chat_interface(context_data, st.session_state.selected_model)


def interview_analysis_page():
    """採用面談分析ページ"""
    logger.info("採用面談分析ページ開始")

    # モード名を最上部に表示
    st.markdown("# 🎯 採用面談分析モード")

    # APIキーの確認
    if not validate_api_key():
        return

    # システム要件チェック
    requirements_met, issues = check_system_requirements()
    if not requirements_met:
        st.error("⚠️ システム要件が満たされていません:")
        for issue in issues:
            st.write(f"- {issue}")
        return

    # サイドバーでモデル選択
    with st.sidebar:
        st.markdown("### ⚙️ 設定")
        selected_model = st.selectbox(
            "GPTモデルを選択:",
            AVAILABLE_MODELS,
            index=AVAILABLE_MODELS.index(
                GPT_MODEL) if GPT_MODEL in AVAILABLE_MODELS else 0,
            help="高性能モデルほど精度が高いですが、費用も高くなります"
        )

    # 募集要項入力
    st.markdown("### 📋 募集要項")
    job_description = st.text_area(
        "募集要項を入力してください",
        placeholder="職種、必要なスキル、経験、人物像などを詳しく記載してください...",
        height=150
    )

    # ファイルアップロード
    st.markdown("### 📁 面接音声ファイルアップロード")
    uploaded_file = st.file_uploader(
        "面接音声ファイルを選択してください",
        type=['mp3', 'wav', 'm4a', 'flac', 'ogg'],
        help="対応形式: MP3, WAV, M4A, FLAC, OGG（最大200MB）"
    )

    if uploaded_file is not None and job_description.strip():
        logger.info(f"ファイルアップロード: {uploaded_file.name}")

        # ファイル情報表示
        st.info(f"📄 ファイル名: {uploaded_file.name}")
        st.info(f"📊 ファイルサイズ: {uploaded_file.size / 1024 / 1024:.2f} MB")

        # 処理開始ボタン
        if st.button("🚀 面接分析を開始", type="primary"):
            logger.info("面接分析処理開始")

            try:
                # プロセッサーの取得
                audio_processor = get_audio_processor()
                text_processor = get_text_processor()

                # ステップ1: 文字起こし
                display_processing_status(1, 5, "音声ファイルを文字起こし中...")
                transcript = audio_processor.transcribe_audio(uploaded_file)

                if transcript is None:
                    st.error("❌ 文字起こしに失敗しました")
                    return

                # ステップ2: 文字起こしブラッシュアップ
                display_processing_status(2, 5, "文字起こしを整形中...")
                brushed_transcript = text_processor.brushup_transcript(
                    transcript, selected_model)

                # ステップ3: 面接要約生成
                display_processing_status(3, 5, "面接要約を生成中...")
                interview_summary = text_processor.generate_interview_summary(
                    brushed_transcript, job_description, selected_model
                )

                # ステップ4: 質問フィードバック生成
                display_processing_status(4, 5, "質問フィードバックを生成中...")
                feedback = text_processor.generate_interview_feedback(
                    brushed_transcript, selected_model)

                # ステップ5: 採用判断材料生成
                display_processing_status(5, 5, "採用判断材料を生成中...")
                decision = text_processor.generate_hiring_decision(
                    brushed_transcript, job_description, selected_model
                )

                logger.info("面接分析処理完了")

                # 結果をセッション状態に保存
                st.session_state.analysis_completed = True
                st.session_state.transcript = transcript
                st.session_state.brushed_transcript = brushed_transcript
                st.session_state.interview_summary = interview_summary
                st.session_state.feedback = feedback
                st.session_state.decision = decision
                st.session_state.job_description = job_description
                st.session_state.selected_model = selected_model

                st.success("✅ 処理が完了しました！")
                st.rerun()

            except Exception as e:
                st.error(f"❌ 処理中にエラーが発生しました: {e}")
                logger.error(f"面接分析処理エラー: {e}", exc_info=True)

    elif uploaded_file is not None and not job_description.strip():
        st.warning("⚠️ 募集要項を入力してください")

    # 結果表示
    if st.session_state.get('analysis_completed', False) and 'interview_summary' in st.session_state:
        st.markdown("---")
        st.markdown("## 📋 分析結果")

        # タブで結果を表示
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📄 元の文字起こし", "✨ 整形済み文字起こし", "📊 面接要約",
            "💬 質問フィードバック", "🎯 採用判断材料", "🤖 AIチャット"
        ])

        with tab1:
            st.markdown("### 📄 元の文字起こし結果")
            st.text_area(
                label="元の文字起こし内容",
                value=st.session_state.transcript,
                height=300,
                disabled=True,
                label_visibility="collapsed"
            )
            create_download_button(
                st.session_state.transcript,
                f"interview_transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                "📥 文字起こしをダウンロード"
            )

        with tab2:
            st.markdown("### ✨ 整形済み文字起こし結果")
            st.text_area(
                label="整形済み文字起こし内容",
                value=st.session_state.brushed_transcript,
                height=300,
                disabled=True,
                label_visibility="collapsed"
            )
            create_download_button(
                st.session_state.brushed_transcript,
                f"interview_brushed_transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                "📥 整形済み文字起こしをダウンロード"
            )

        with tab3:
            st.markdown("### 📊 面接要約")
            st.markdown(st.session_state.interview_summary)
            create_download_button(
                st.session_state.interview_summary,
                f"interview_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                "📥 面接要約をダウンロード"
            )

        with tab4:
            st.markdown("### 💬 質問フィードバック")
            st.markdown(st.session_state.feedback)
            create_download_button(
                st.session_state.feedback,
                f"interview_feedback_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                "📥 質問フィードバックをダウンロード"
            )

        with tab5:
            st.markdown("### 🎯 採用判断材料")
            st.markdown(st.session_state.decision)
            create_download_button(
                st.session_state.decision,
                f"hiring_decision_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                "📥 採用判断材料をダウンロード"
            )

        with tab6:
            # チャットインターフェース
            context_data = {
                'transcript': st.session_state.transcript,
                'brushed_transcript': st.session_state.brushed_transcript,
                'summary': st.session_state.interview_summary,
                'feedback': st.session_state.feedback,
                'decision': st.session_state.decision,
                'job_description': st.session_state.job_description
            }
            chat_interface(context_data, st.session_state.selected_model)


def main():
    """メイン関数"""
    logger.info("メインページ開始")

    # サイドバーでモード選択
    with st.sidebar:
        st.markdown("# 🎤 音声処理アプリ")
        st.markdown("---")

        mode = st.radio(
            "機能を選択してください:",
            ["議事録要約", "採用面談分析"],
            key="mode_selection"
        )

        st.markdown("---")
        st.markdown("### 📖 使い方")
        if mode == "議事録要約":
            st.markdown("""
            1. 音声ファイルをアップロード
            2. GPTモデルを選択
            3. 「議事録要約を開始」をクリック
            4. 結果を確認・ダウンロード
            5. AIチャットで詳細質問
            """)
        else:
            st.markdown("""
            1. 募集要項を入力
            2. 面接音声ファイルをアップロード
            3. GPTモデルを選択
            4. 「面接分析を開始」をクリック
            5. 各タブで結果を確認
            6. AIチャットで詳細質問
            """)

    # セッション状態の初期化
    if 'analysis_completed' not in st.session_state:
        st.session_state.analysis_completed = False

    # モードに応じてページを表示
    logger.info(f"現在のモード: {mode}")
    logger.info(f"分析完了状態: {st.session_state.analysis_completed}")

    if mode == "議事録要約":
        meeting_summary_page()
    else:
        interview_analysis_page()


if __name__ == "__main__":
    main()
