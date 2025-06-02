import json
import logging
import os
import sys
import tempfile
from datetime import datetime

import boto3
import librosa
import soundfile as sf
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TranscribeProcessor:
    def __init__(self):
        """音声文字起こし処理クラスの初期化"""
        self.s3_client = boto3.client('s3')
        self.model = None
        self.processor = None
        self.pipe = None

    def load_model(self):
        """kotoba-whisper-v2.0モデルの読み込み"""
        try:
            logger.info("kotoba-whisper-v2.0モデルを読み込み中...")

            device = "cuda:0" if torch.cuda.is_available() else "cpu"
            torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

            model_id = "kotoba-tech/kotoba-whisper-v2.0"

            # モデルとプロセッサーの読み込み
            self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
                model_id,
                torch_dtype=torch_dtype,
                low_cpu_mem_usage=True,
                use_safetensors=True
            )
            self.model.to(device)

            self.processor = AutoProcessor.from_pretrained(model_id)

            # パイプラインの作成
            self.pipe = pipeline(
                "automatic-speech-recognition",
                model=self.model,
                tokenizer=self.processor.tokenizer,
                feature_extractor=self.processor.feature_extractor,
                max_new_tokens=128,
                chunk_length_s=30,
                batch_size=16,
                return_timestamps=True,
                torch_dtype=torch_dtype,
                device=device,
            )

            logger.info("モデルの読み込みが完了しました")

        except Exception as e:
            logger.error(f"モデル読み込みエラー: {str(e)}")
            raise

    def download_audio_from_s3(self, bucket, key):
        """S3から音声ファイルをダウンロード"""
        try:
            logger.info(f"S3から音声ファイルをダウンロード中: s3://{bucket}/{key}")

            # 一時ファイルを作成
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix='.wav')
            temp_path = temp_file.name
            temp_file.close()

            # S3からファイルをダウンロード
            self.s3_client.download_file(bucket, key, temp_path)

            logger.info(f"ダウンロード完了: {temp_path}")
            return temp_path

        except Exception as e:
            logger.error(f"S3ダウンロードエラー: {str(e)}")
            raise

    def preprocess_audio(self, audio_path):
        """音声ファイルの前処理"""
        try:
            logger.info("音声ファイルの前処理中...")

            # 音声ファイルを読み込み（16kHzにリサンプリング）
            audio, sr = librosa.load(audio_path, sr=16000)

            # 音声の長さをチェック
            duration = len(audio) / sr
            logger.info(f"音声の長さ: {duration:.2f}秒")

            return audio

        except Exception as e:
            logger.error(f"音声前処理エラー: {str(e)}")
            raise

    def transcribe_audio(self, audio):
        """音声の文字起こし実行"""
        try:
            logger.info("文字起こし処理を開始...")

            # 文字起こし実行
            result = self.pipe(audio)

            logger.info("文字起こし処理が完了しました")
            return result

        except Exception as e:
            logger.error(f"文字起こしエラー: {str(e)}")
            raise

    def process(self, input_data):
        """メイン処理"""
        try:
            # 入力データの検証
            if 'bucket' not in input_data or 'key' not in input_data:
                raise ValueError("入力データにbucketまたはkeyが含まれていません")

            bucket = input_data['bucket']
            key = input_data['key']

            logger.info(f"処理開始 - Bucket: {bucket}, Key: {key}")

            # モデルの読み込み
            if self.model is None:
                self.load_model()

            # S3から音声ファイルをダウンロード
            audio_path = self.download_audio_from_s3(bucket, key)

            try:
                # 音声の前処理
                audio = self.preprocess_audio(audio_path)

                # 文字起こし実行
                transcription_result = self.transcribe_audio(audio)

                # 結果の整形
                output = {
                    "status": "success",
                    "timestamp": datetime.utcnow().isoformat(),
                    "input": {
                        "bucket": bucket,
                        "key": key
                    },
                    "transcription": {
                        "text": transcription_result.get("text", ""),
                        "chunks": transcription_result.get("chunks", [])
                    },
                    "metadata": {
                        "model": "kotoba-whisper-v2.0",
                        "audio_duration": len(audio) / 16000 if audio is not None else 0
                    }
                }

                logger.info("処理が正常に完了しました")
                return output

            finally:
                # 一時ファイルの削除
                if os.path.exists(audio_path):
                    os.unlink(audio_path)
                    logger.info("一時ファイルを削除しました")

        except Exception as e:
            logger.error(f"処理エラー: {str(e)}")
            return {
                "status": "error",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
                "input": input_data
            }


def main():
    """メイン関数"""
    try:
        # 環境変数または標準入力から入力データを取得
        input_json = os.environ.get('INPUT_JSON')

        if not input_json:
            # 標準入力から読み取り
            input_json = sys.stdin.read().strip()

        if not input_json:
            raise ValueError("入力データが提供されていません")

        # JSON解析
        input_data = json.loads(input_json)

        # 処理実行
        processor = TranscribeProcessor()
        result = processor.process(input_data)

        # 結果を標準出力に出力
        print(json.dumps(result, ensure_ascii=False, indent=2))

        # 成功時は終了コード0、エラー時は1
        sys.exit(0 if result.get("status") == "success" else 1)

    except Exception as e:
        error_result = {
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }
        print(json.dumps(error_result, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
