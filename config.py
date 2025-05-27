import logging
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()

# === 基本設定 ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
GPT_MODEL = os.getenv("GPT_MODEL", "gpt-3.5-turbo")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# === ディレクトリ設定 ===
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "outputs"
LOG_DIR = BASE_DIR / "logs"
UPLOAD_DIR = BASE_DIR / "uploads"

# ディレクトリを作成
OUTPUT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

# === ファイル設定 ===
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB
ALLOWED_EXTENSIONS = ['.mp3', '.wav', '.m4a', '.flac', '.ogg']

# === トークン管理設定 ===
CONTEXT_LIMIT_PERCENTAGE = 0.5  # コンテキスト上限の50%
MODEL_TOKEN_LIMITS = {
    "gpt-3.5-turbo": 4096,
    "gpt-4": 8192,
    "gpt-4-turbo": 128000,
    "gpt-4o": 128000,
}

# === ログ設定 ===


def setup_logging():
    """ログ設定を初期化"""
    from datetime import datetime

    # ログレベルの設定
    log_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    # ログファイル名（日付付き）
    log_filename = LOG_DIR / f"app_{datetime.now().strftime('%Y%m%d')}.log"

    # ログフォーマット
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )

    # ファイルハンドラー
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # コンソールハンドラー
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.WARNING)  # コンソールは警告以上のみ

    # ルートロガーの設定
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return root_logger


def get_logger(name):
    """指定された名前のロガーを取得"""
    return logging.getLogger(name)


# ログ設定を初期化
setup_logging()
logger = get_logger(__name__)
logger.info("=== 音声処理アプリケーション開始 ===")

# === システム要件チェック ===


def check_ffmpeg():
    """ffmpegの存在をチェック"""
    try:
        # ffmpegコマンドの実行を試行
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            # ffmpegのパスを取得
            ffmpeg_path = subprocess.run(
                ['where', 'ffmpeg'] if os.name == 'nt' else ['which', 'ffmpeg'],
                capture_output=True,
                text=True
            ).stdout.strip()

            logger.info(f"ffmpeg発見: {ffmpeg_path}")
            return True, ffmpeg_path
        else:
            logger.error("ffmpegコマンドの実行に失敗")
            return False, None

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error(f"ffmpegが見つかりません: {e}")
        return False, None


def check_system_requirements():
    """システム要件をチェック"""
    requirements_met = True
    issues = []

    # ffmpegチェック
    ffmpeg_available, ffmpeg_path = check_ffmpeg()
    if not ffmpeg_available:
        requirements_met = False
        issues.append("ffmpegが見つかりません")
        logger.error("システム要件エラー: ffmpegが見つかりません")

    # OpenAI APIキーチェック
    if not OPENAI_API_KEY:
        requirements_met = False
        issues.append("OpenAI APIキーが設定されていません")
        logger.error("システム要件エラー: OpenAI APIキーが設定されていません")

    if requirements_met:
        logger.info("システム要件チェック完了: すべてOK")
    else:
        logger.warning(f"システム要件チェック: 一部の要件が満たされていません - {', '.join(issues)}")

    return requirements_met, issues


# === GPTモデル選択肢 ===
AVAILABLE_MODELS = [
    "gpt-3.5-turbo",
    "gpt-4",
    "gpt-4-turbo",
    "gpt-4o"
]

# === プロンプトテンプレート ===
MEETING_SUMMARY_PROMPT = """
以下の会議の文字起こしを基に、簡潔で分かりやすい議事録を作成してください。

【文字起こし】
{transcript}

【出力形式】
# 会議議事録

## 📅 概要
- 日時: [推定される日時]
- 参加者: [推定される参加者]

## 📋 主な議題
1. [議題1]
2. [議題2]

## 💬 主な内容
[重要な発言や決定事項を要約]

## ✅ 決定事項
- [決定事項1]
- [決定事項2]

## 📝 次回までのアクション
- [アクション項目1]
- [アクション項目2]
"""

TRANSCRIPT_BRUSHUP_PROMPT = """
以下の音声文字起こし結果を、読みやすく自然な日本語に修正してください。
誤字脱字の修正、意味不明な箇所の推測修正、適切な句読点の追加を行ってください。
ただし、話者の意図や内容は変更せず、元の意味を保持してください。

【元の文字起こし】
{transcript}

【修正後の文字起こし】
"""

INTERVIEW_SUMMARY_PROMPT = """
以下の面接の文字起こしと募集要項を基に、面接の要約を作成してください。

【募集要項】
{job_description}

【面接文字起こし】
{transcript}

【出力形式】
# 面接要約

## 👤 候補者プロフィール
[候補者の基本情報や経歴]

## 💼 主な質疑応答
[重要な質問と回答の要約]

## 🎯 募集要項との適合性
[募集要項の要件に対する候補者の適合度]

## 💡 印象・特記事項
[面接官の印象や特筆すべき点]
"""

INTERVIEW_FEEDBACK_PROMPT = """
以下の面接の文字起こしを基に、面接官の質問に対するフィードバックを提供してください。

【面接文字起こし】
{transcript}

【出力形式】
# 面接官質問フィードバック

## ✅ 良かった質問
[効果的だった質問とその理由]

## ⚠️ 改善できる質問
[より良くできる質問とその改善案]

## 💡 追加推奨質問
[聞いておくべきだった質問の提案]

## 📊 質問の傾向分析
[質問の種類や傾向の分析]
"""

HIRING_DECISION_PROMPT = """
以下の面接の文字起こしと募集要項を基に、採用判断の材料を提供してください。

【募集要項】
{job_description}

【面接文字起こし】
{transcript}

【出力形式】
# 採用判断材料

## ✅ 強み・プラス要因
[候補者の強みや採用に有利な要因]

## ⚠️ 懸念点・リスク要因
[気になる点や採用リスク]

## 🎯 募集要項適合度
[各要件に対する適合度の詳細評価]

## 💰 給与・条件面の考慮事項
[給与交渉や条件面での考慮点]

## 📋 総合評価
[総合的な採用推奨度と理由]
"""
