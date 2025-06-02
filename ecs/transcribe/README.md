# 音声文字起こしECSアプリケーション

このアプリケーションは、AWS ECS上でkotoba-whisper-v2.0モデルを使用して音声ファイルの文字起こしを行います。

## 概要

- **入力**: S3上の音声ファイル（bucket名とkey名）
- **処理**: kotoba-whisper-v2.0による日本語音声文字起こし
- **出力**: 文字起こし結果のJSON

## ファイル構成

```
ecs/transcribe/
├── app.py                    # メインアプリケーション
├── requirements.txt          # Python依存関係
├── Dockerfile               # Dockerイメージ定義
├── buildspec.yml            # CodeBuild設定ファイル
├── codebuild-policy.json    # CodeBuild IAMポリシー
├── deploy.sh                # 自動デプロイスクリプト
└── README.md               # このファイル
```

## 入力形式

```json
{
  "bucket": "your-audio-bucket",
  "key": "path/to/audio/file.wav"
}
```

## 出力形式

### 成功時
```json
{
  "status": "success",
  "timestamp": "2024-01-01T12:00:00.000000",
  "input": {
    "bucket": "your-audio-bucket",
    "key": "path/to/audio/file.wav"
  },
  "transcription": {
    "text": "文字起こし結果のテキスト",
    "chunks": [
      {
        "timestamp": [0.0, 5.0],
        "text": "最初の5秒間の文字起こし"
      }
    ]
  },
  "metadata": {
    "model": "kotoba-whisper-v2.0",
    "audio_duration": 30.5
  }
}
```

### エラー時
```json
{
  "status": "error",
  "timestamp": "2024-01-01T12:00:00.000000",
  "error": "エラーメッセージ",
  "input": {
    "bucket": "your-audio-bucket",
    "key": "path/to/audio/file.wav"
  }
}
```

## デプロイ方法

### 前提条件
- AWS CLIが設定済み
- GitHubリポジトリにコードがプッシュ済み
- 適切なAWS権限を持つIAMユーザー/ロール

### 手順

1. **GitHubリポジトリの設定**
   ```bash
   # コードをGitHubにプッシュ
   git add .
   git commit -m "Add transcribe ECS application"
   git push origin main
   ```

2. **デプロイスクリプトの設定**
   ```bash
   # deploy.shのSOURCE_LOCATIONを実際のGitHubリポジトリURLに変更
   vim ecs/transcribe/deploy.sh
   # SOURCE_LOCATION="https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git"
   ```

3. **自動デプロイの実行**
   ```bash
   cd ecs/transcribe
   ./deploy.sh
   ```

このスクリプトは以下を自動実行します：
- ECRリポジトリの作成
- CloudWatch Logsグループの作成
- CodeBuildサービスロールの作成
- CodeBuildプロジェクトの作成
- ビルドの実行と監視
- ECSタスク定義の更新

### CodeBuildプロジェクトの手動実行
```bash
# 既存のプロジェクトでビルドを実行
aws codebuild start-build --project-name transcribe-app-build
```

## IAMロールの設定

### ECSタスク実行ロール
- `AmazonECSTaskExecutionRolePolicy`

### ECSタスクロール
- S3読み取り権限
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::your-audio-bucket/*"
    }
  ]
}
```

### CodeBuildサービスロール
- `codebuild-policy.json`に定義されたカスタムポリシー
- ECR、ECS、CloudWatch Logs、IAMの必要な権限

## Step Functions統合

このECSタスクはStep Functionsから起動されることを想定しています。

### Step Functions状態定義例

```json
{
  "Comment": "音声文字起こし処理",
  "StartAt": "TranscribeAudio",
  "States": {
    "TranscribeAudio": {
      "Type": "Task",
      "Resource": "arn:aws:states:::ecs:runTask.sync",
      "Parameters": {
        "TaskDefinition": "transcribe-task",
        "Cluster": "your-ecs-cluster",
        "LaunchType": "FARGATE",
        "NetworkConfiguration": {
          "AwsvpcConfiguration": {
            "Subnets": ["subnet-12345"],
            "SecurityGroups": ["sg-12345"],
            "AssignPublicIp": "ENABLED"
          }
        },
        "Overrides": {
          "ContainerOverrides": [
            {
              "Name": "transcribe-container",
              "Environment": [
                {
                  "Name": "INPUT_JSON",
                  "Value.$": "$"
                }
              ]
            }
          ]
        }
      },
      "End": true
    }
  }
}
```

## ローカルテスト

```bash
# 入力データを環境変数で設定
export INPUT_JSON='{"bucket":"test-bucket","key":"test-audio.wav"}'

# アプリケーションを実行
python app.py
```

## CI/CDパイプライン

CodeBuildプロジェクトは以下の処理を自動実行します：

1. **pre_build**: ECRログイン、環境変数設定
2. **build**: Dockerイメージのビルドとタグ付け
3. **post_build**: ECRへのプッシュ、ECSタスク定義の更新

### 環境変数
- `AWS_DEFAULT_REGION`: ap-northeast-1
- `AWS_ACCOUNT_ID`: 458575205268
- `IMAGE_REPO_NAME`: transcribe-app

## 監視とログ

- **CodeBuildログ**: `/aws/codebuild/transcribe-app-build`
- **ECSタスクログ**: `/ecs/transcribe-task`
- **CloudWatchメトリクス**: ECSタスクの実行状況

## トラブルシューティング

### よくある問題

1. **ECR認証エラー**
   ```bash
   aws ecr get-login-password --region ap-northeast-1 | docker login --username AWS --password-stdin 458575205268.dkr.ecr.ap-northeast-1.amazonaws.com
   ```

2. **IAM権限不足**
   - CodeBuildサービスロールの権限を確認
   - ECSタスクロールの権限を確認

3. **メモリ不足**
   - ECSタスク定義のメモリを8GB以上に設定

## 注意事項

- kotoba-whisper-v2.0は大きなモデルのため、十分なメモリ（8GB以上推奨）が必要です
- GPU使用時はより高速に処理できますが、CPUでも動作します
- 音声ファイルは自動的に16kHzにリサンプリングされます
- 処理時間は音声の長さに比例します（目安：1分の音声で30秒〜2分程度）
- CodeBuildでのビルド時間は約10-15分程度かかります（初回はモデルダウンロードのため更に時間がかかる場合があります） 