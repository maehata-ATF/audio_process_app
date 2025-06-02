# Python 3.10ベースイメージを使用
FROM python:3.10-slim

# 作業ディレクトリを設定
WORKDIR /app

# システムパッケージの更新とffmpegのインストール
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Pythonの依存関係をコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY app.py .

# 環境変数の設定
ENV PYTHONUNBUFFERED=1
ENV TRANSFORMERS_CACHE=/tmp/transformers_cache
ENV HF_HOME=/tmp/huggingface_cache

# キャッシュディレクトリの作成
RUN mkdir -p /tmp/transformers_cache /tmp/huggingface_cache

# アプリケーションの実行
CMD ["python", "app.py"] 