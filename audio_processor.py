import os
import tempfile
import warnings
from pathlib import Path

import streamlit as st
import torch
import whisper

from config import WHISPER_MODEL, check_ffmpeg, get_logger

# Whisperの警告を抑制
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")


class AudioProcessor:
    def __init__(self):
        self.model = None
        self.logger = get_logger(__name__)
        self.logger.info("AudioProcessor初期化")

        # ffmpegの存在をチェック
        self.ffmpeg_available, self.ffmpeg_path = check_ffmpeg()
        if not self.ffmpeg_available:
            self.logger.error("ffmpegが利用できません - 音声処理に必要")

    @st.cache_resource
    def load_whisper_model(_self):
        """Whisperモデルを読み込む"""
        logger = get_logger(__name__)
        try:
            logger.info(f"Whisperモデル読み込み開始: {WHISPER_MODEL}")

            # CPUの場合はFP32を強制使用
            if not torch.cuda.is_available():
                logger.info("CPUモード: FP32を使用")

            model = whisper.load_model(WHISPER_MODEL)
            logger.info(f"Whisperモデル読み込み完了: {WHISPER_MODEL}")
            return model
        except Exception as e:
            logger.error(f"Whisperモデルの読み込みに失敗: {e}", exc_info=True)
            st.error(f"Whisperモデルの読み込みに失敗しました: {e}")
            return None

    def transcribe_audio(self, audio_file):
        """
        音声ファイルを文字起こしする

        Args:
            audio_file: アップロードされた音声ファイル

        Returns:
            str: 文字起こし結果
        """
        # ffmpegの存在チェック
        if not self.ffmpeg_available:
            error_msg = ("音声処理に必要なffmpegが見つかりません。\n"
                         "ffmpegをインストールしてください。")
            self.logger.error(f"ffmpeg未インストール: {error_msg}")
            st.error(f"❌ {error_msg}")
            return None

        if self.model is None:
            self.model = self.load_whisper_model()

        if self.model is None:
            self.logger.error("Whisperモデルが利用できません")
            return None

        tmp_file_path = None
        try:
            self.logger.info(f"文字起こし開始: {audio_file.name}")

            # ファイルサイズをログに記録
            file_size = audio_file.size
            self.logger.info(f"ファイルサイズ: {file_size} bytes")

            # 一時ファイルに保存
            file_extension = Path(audio_file.name).suffix.lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
                tmp_file.write(audio_file.read())
                tmp_file_path = tmp_file.name

            self.logger.info(f"一時ファイル作成: {tmp_file_path}")

            # Whisperで文字起こし
            self.logger.info("Whisper文字起こし実行中...")

            # 警告を抑制して実行
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                result = self.model.transcribe(
                    tmp_file_path,
                    language="ja",
                    fp16=False  # CPUでも安全に実行
                )

            transcript = result["text"]
            transcript_length = len(transcript)

            self.logger.info(f"文字起こし完了: 文字数={transcript_length}")
            self.logger.debug(f"文字起こし結果（最初の100文字）: {transcript[:100]}...")

            # 一時ファイルを削除
            os.unlink(tmp_file_path)
            self.logger.info("一時ファイル削除完了")

            return transcript

        except FileNotFoundError as e:
            self.logger.error(f"ファイル不見エラー（おそらくffmpeg関連）: {e}", exc_info=True)

            # より詳細なエラー情報をログに記録
            self.logger.error(f"ファイル名: {audio_file.name}")
            self.logger.error(f"ファイルサイズ: {audio_file.size}")
            self.logger.error(f"一時ファイルパス: {tmp_file_path}")
            self.logger.error(f"ffmpeg利用可能: {self.ffmpeg_available}")

            # ユーザーに分かりやすいエラーメッセージを表示
            error_msg = ("音声処理に失敗しました。\n"
                         "ffmpegが正しくインストールされていない可能性があります。\n"
                         "詳細はログファイルをご確認ください。")
            st.error(f"❌ {error_msg}")

            # 一時ファイルの削除を試行
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.unlink(tmp_file_path)
                    self.logger.info("エラー後の一時ファイル削除完了")
                except Exception as cleanup_error:
                    self.logger.error(f"一時ファイル削除に失敗: {cleanup_error}")

            return None

        except Exception as e:
            self.logger.error(f"文字起こしに失敗: {e}", exc_info=True)

            # より詳細なエラー情報をログに記録
            self.logger.error(f"ファイル名: {audio_file.name}")
            self.logger.error(f"ファイルサイズ: {audio_file.size}")
            self.logger.error(f"一時ファイルパス: {tmp_file_path}")

            # 一時ファイルの削除を試行
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.unlink(tmp_file_path)
                    self.logger.info("エラー後の一時ファイル削除完了")
                except Exception as cleanup_error:
                    self.logger.error(f"一時ファイル削除に失敗: {cleanup_error}")

            st.error(f"文字起こしに失敗しました: {e}")
            return None

    def validate_audio_file(self, audio_file):
        """
        音声ファイルの妥当性をチェック

        Args:
            audio_file: アップロードされたファイル

        Returns:
            tuple: (bool, str) 妥当性の結果とメッセージ
        """
        self.logger.info("音声ファイル妥当性チェック開始")

        if audio_file is None:
            self.logger.warning("ファイルがアップロードされていません")
            return False, "ファイルがアップロードされていません"

        # ファイル拡張子のチェック
        allowed_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.ogg']
        file_extension = Path(audio_file.name).suffix.lower()

        self.logger.info(
            f"ファイル情報: 名前={audio_file.name}, 拡張子={file_extension}, サイズ={audio_file.size}")

        if file_extension not in allowed_extensions:
            error_msg = f"サポートされていないファイル形式です。対応形式: {', '.join(allowed_extensions)}"
            self.logger.warning(f"ファイル形式エラー: {error_msg}")
            return False, error_msg

        # ファイルサイズのチェック
        if audio_file.size > 200 * 1024 * 1024:  # 200MB
            error_msg = "ファイルサイズが大きすぎます（最大200MB）"
            self.logger.warning(f"ファイルサイズエラー: サイズ={audio_file.size}")
            return False, error_msg

        # ファイルが空でないかチェック
        if audio_file.size == 0:
            error_msg = "ファイルが空です"
            self.logger.warning("空ファイルエラー")
            return False, error_msg

        self.logger.info("音声ファイル妥当性チェック完了: OK")
        return True, "OK"
