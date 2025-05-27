from datetime import datetime
from typing import Any, Dict, List, Optional

import tiktoken
from openai import OpenAI

from config import (CONTEXT_LIMIT_PERCENTAGE, GPT_MODEL,
                    HIRING_DECISION_PROMPT, INTERVIEW_FEEDBACK_PROMPT,
                    INTERVIEW_SUMMARY_PROMPT, MEETING_SUMMARY_PROMPT,
                    MODEL_TOKEN_LIMITS, OPENAI_API_KEY,
                    TRANSCRIPT_BRUSHUP_PROMPT, get_logger)


class ChatMessage:
    """チャットメッセージクラス"""

    def __init__(self, role: str, content: str, timestamp: datetime = None):
        self.role = role  # "user" or "assistant"
        self.content = content
        self.timestamp = timestamp or datetime.now()

    def to_dict(self) -> Dict[str, str]:
        """OpenAI API用の辞書形式に変換"""
        return {"role": self.role, "content": self.content}


class ChatHistory:
    """チャット履歴管理クラス"""

    def __init__(self):
        self.messages: List[ChatMessage] = []
        self.logger = get_logger(__name__)

    def add_message(self, role: str, content: str):
        """メッセージを追加"""
        message = ChatMessage(role, content)
        self.messages.append(message)
        self.logger.info(f"チャット履歴追加: {role} - {len(content)}文字")

    def get_messages_for_api(self) -> List[Dict[str, str]]:
        """OpenAI API用のメッセージリストを取得"""
        return [msg.to_dict() for msg in self.messages]

    def clear(self):
        """履歴をクリア"""
        self.messages.clear()
        self.logger.info("チャット履歴をクリア")

    def remove_oldest(self):
        """最古のメッセージを削除"""
        if self.messages:
            removed = self.messages.pop(0)
            self.logger.info(
                f"最古のメッセージを削除: {removed.role} - {len(removed.content)}文字")
            return removed
        return None

    def get_total_tokens(self, model: str) -> int:
        """現在の履歴の総トークン数を計算"""
        try:
            encoding = tiktoken.encoding_for_model(model)
            total_tokens = 0

            for message in self.messages:
                # メッセージのトークン数を計算
                message_tokens = len(encoding.encode(message.content))
                # ロール情報のオーバーヘッドを追加（約4トークン）
                total_tokens += message_tokens + 4

            return total_tokens
        except Exception as e:
            # tiktokenでエラーが発生した場合は概算値を返す
            total_chars = sum(len(msg.content) for msg in self.messages)
            return total_chars // 3  # 日本語の場合、約3文字で1トークン


class TextProcessor:
    """テキスト処理クラス"""

    def __init__(self):
        self.logger = get_logger(__name__)
        self.logger.info("TextProcessor初期化")

        # OpenAIクライアントの初期化
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.logger.info("OpenAI クライアント初期化完了")

        # チャット履歴の初期化
        self.chat_history = ChatHistory()

    def count_tokens(self, text: str, model: str) -> int:
        """テキストのトークン数をカウント"""
        try:
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(text))
        except Exception as e:
            self.logger.warning(f"トークンカウントでエラー: {e}")
            # フォールバック: 文字数を3で割った概算値
            return len(text) // 3

    def manage_context_limit(self, model: str, additional_tokens: int = 0):
        """コンテキスト制限を管理"""
        max_tokens = MODEL_TOKEN_LIMITS.get(model, 4096)
        limit_tokens = int(max_tokens * CONTEXT_LIMIT_PERCENTAGE)

        current_tokens = self.chat_history.get_total_tokens(model)
        total_tokens = current_tokens + additional_tokens

        self.logger.info(
            f"トークン管理: 現在={current_tokens}, 追加={additional_tokens}, 制限={limit_tokens}")

        # 制限を超えている場合、古い履歴を削除
        while total_tokens > limit_tokens and self.chat_history.messages:
            removed = self.chat_history.remove_oldest()
            if removed:
                current_tokens = self.chat_history.get_total_tokens(model)
                total_tokens = current_tokens + additional_tokens
                self.logger.info(f"制限超過により履歴削除: 新しい合計={total_tokens}")
            else:
                break

        # 履歴が空でも制限を超える場合は警告のみ
        if total_tokens > limit_tokens:
            self.logger.warning(f"履歴が空でも制限超過: {total_tokens} > {limit_tokens}")

    def validate_inputs(self, transcript: str, job_description: str = None) -> bool:
        """入力の妥当性をチェック"""
        self.logger.info("入力妥当性チェック開始")

        if not transcript or len(transcript.strip()) == 0:
            self.logger.error("文字起こしが空です")
            return False

        if len(transcript) < 10:
            self.logger.warning("文字起こしが短すぎます")

        if job_description is not None and len(job_description.strip()) == 0:
            self.logger.error("募集要項が空です")
            return False

        self.logger.info("入力妥当性チェック完了: OK")
        return True

    def brushup_transcript(self, transcript: str, model: str = None) -> str:
        """文字起こしをブラッシュアップ"""
        if model is None:
            model = GPT_MODEL

        self.logger.info("文字起こしブラッシュアップ開始")
        self.logger.info(f"入力テキスト長: {len(transcript)} 文字")

        prompt = TRANSCRIPT_BRUSHUP_PROMPT.format(transcript=transcript)

        try:
            self.logger.info("OpenAI API呼び出し開始 - 文字起こしブラッシュアップ")

            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system",
                        "content": "あなたは音声文字起こしの修正専門家です。誤字脱字を修正し、自然な日本語に整形してください。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )

            brushed_transcript = response.choices[0].message.content.strip()

            self.logger.info(
                f"文字起こしブラッシュアップ完了 - 出力長: {len(brushed_transcript)} 文字")
            return brushed_transcript

        except Exception as e:
            self.logger.error(f"文字起こしブラッシュアップに失敗: {e}", exc_info=True)
            return transcript  # エラー時は元のテキストを返す

    def generate_meeting_summary(self, transcript: str, model: str = None) -> str:
        """議事録要約を生成"""
        if model is None:
            model = GPT_MODEL

        self.logger.info("議事録要約生成開始")
        self.logger.info(f"入力テキスト長: {len(transcript)} 文字")

        prompt = MEETING_SUMMARY_PROMPT.format(transcript=transcript)
        self.logger.info(f"プロンプト長: {len(prompt)} 文字")

        try:
            self.logger.info(f"OpenAI API呼び出し開始 - モデル: {model}")

            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system",
                        "content": "あなたは議事録作成の専門家です。会議の内容を整理し、分かりやすい議事録を作成してください。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )

            summary = response.choices[0].message.content.strip()

            self.logger.info(f"議事録要約生成完了 - 出力長: {len(summary)} 文字")
            return summary

        except Exception as e:
            self.logger.error(f"議事録要約生成に失敗: {e}", exc_info=True)
            raise

    def generate_interview_summary(self, transcript: str, job_description: str, model: str = None) -> str:
        """面接要約を生成"""
        if model is None:
            model = GPT_MODEL

        self.logger.info("面接要約生成開始")
        self.logger.info(
            f"入力 - 文字起こし長: {len(transcript)} 文字, 募集要項長: {len(job_description)} 文字")

        prompt = INTERVIEW_SUMMARY_PROMPT.format(
            transcript=transcript,
            job_description=job_description
        )

        try:
            self.logger.info(f"OpenAI API呼び出し開始 - モデル: {model}")

            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "あなたは採用面接の分析専門家です。面接内容を客観的に分析し、要約してください。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )

            summary = response.choices[0].message.content.strip()

            self.logger.info(f"面接要約生成完了 - 出力長: {len(summary)} 文字")
            return summary

        except Exception as e:
            self.logger.error(f"面接要約生成に失敗: {e}", exc_info=True)
            raise

    def generate_interview_feedback(self, transcript: str, model: str = None) -> str:
        """面接フィードバックを生成"""
        if model is None:
            model = GPT_MODEL

        self.logger.info("質問フィードバック生成開始")

        prompt = INTERVIEW_FEEDBACK_PROMPT.format(transcript=transcript)

        try:
            self.logger.info(f"OpenAI API呼び出し開始 - モデル: {model}")

            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system",
                        "content": "あなたは面接官のコーチングを行う専門家です。質問の質を分析し、改善提案をしてください。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )

            feedback = response.choices[0].message.content.strip()

            self.logger.info(f"質問フィードバック生成完了 - 出力長: {len(feedback)} 文字")
            return feedback

        except Exception as e:
            self.logger.error(f"質問フィードバック生成に失敗: {e}", exc_info=True)
            raise

    def generate_hiring_decision(self, transcript: str, job_description: str, model: str = None) -> str:
        """採用判断材料を生成"""
        if model is None:
            model = GPT_MODEL

        self.logger.info("採用判断材料生成開始")

        prompt = HIRING_DECISION_PROMPT.format(
            transcript=transcript,
            job_description=job_description
        )

        try:
            self.logger.info(f"OpenAI API呼び出し開始 - モデル: {model}")

            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system",
                        "content": "あなたは採用判断のアドバイザーです。客観的な視点で候補者を評価し、採用判断の材料を提供してください。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )

            decision = response.choices[0].message.content.strip()

            self.logger.info(f"採用判断材料生成完了 - 出力長: {len(decision)} 文字")
            return decision

        except Exception as e:
            self.logger.error(f"採用判断材料生成に失敗: {e}", exc_info=True)
            raise

    def chat_with_context(self, user_message: str, context_data: Dict[str, Any], model: str = None) -> str:
        """コンテキスト付きチャット"""
        if model is None:
            model = GPT_MODEL

        self.logger.info("チャット開始")
        self.logger.info(f"ユーザーメッセージ: {user_message}")

        # コンテキスト情報を整理
        context_parts = []
        if context_data.get('transcript'):
            context_parts.append(f"【文字起こし】\n{context_data['transcript']}")
        if context_data.get('brushed_transcript'):
            context_parts.append(
                f"【整形済み文字起こし】\n{context_data['brushed_transcript']}")
        if context_data.get('summary'):
            context_parts.append(f"【要約】\n{context_data['summary']}")
        if context_data.get('job_description'):
            context_parts.append(f"【募集要項】\n{context_data['job_description']}")
        if context_data.get('feedback'):
            context_parts.append(f"【フィードバック】\n{context_data['feedback']}")
        if context_data.get('decision'):
            context_parts.append(f"【採用判断材料】\n{context_data['decision']}")

        context_text = "\n\n".join(context_parts)

        # 初回の場合はシステムメッセージとコンテキストを追加
        if not self.chat_history.messages:
            system_message = "あなたは音声分析の専門家です。提供されたコンテキスト情報を基に、ユーザーの質問に詳しく答えてください。"
            self.chat_history.add_message("system", system_message)

            if context_text:
                context_message = f"以下が分析対象のデータです：\n\n{context_text}"
                self.chat_history.add_message("assistant", context_message)

        # ユーザーメッセージを追加
        self.chat_history.add_message("user", user_message)

        # トークン制限管理
        user_tokens = self.count_tokens(user_message, model)
        self.manage_context_limit(model, user_tokens + 500)  # レスポンス用のバッファ

        try:
            self.logger.info("OpenAI API呼び出し開始 - チャット機能")

            response = self.client.chat.completions.create(
                model=model,
                messages=self.chat_history.get_messages_for_api(),
                temperature=0.7,
                max_tokens=1000
            )

            assistant_response = response.choices[0].message.content.strip()

            # アシスタントの回答を履歴に追加
            self.chat_history.add_message("assistant", assistant_response)

            self.logger.info(f"チャット完了 - 出力長: {len(assistant_response)} 文字")
            return assistant_response

        except Exception as e:
            self.logger.error(f"チャット処理に失敗: {e}", exc_info=True)
            raise

    def clear_chat_history(self):
        """チャット履歴をクリア"""
        self.chat_history.clear()
        self.logger.info("チャット履歴をクリア")

    def get_chat_history_summary(self) -> Dict[str, Any]:
        """チャット履歴の要約情報を取得"""
        return {
            "message_count": len(self.chat_history.messages),
            "total_tokens": self.chat_history.get_total_tokens(GPT_MODEL),
            "oldest_message": self.chat_history.messages[0].timestamp if self.chat_history.messages else None,
            "latest_message": self.chat_history.messages[-1].timestamp if self.chat_history.messages else None
        }
