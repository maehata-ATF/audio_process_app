#!/bin/bash

# 設定変数
PROJECT_NAME="transcribe-app-build"
ACCOUNT_ID="458575205268"
REGION="ap-northeast-1"
IMAGE_REPO_NAME="transcribe-app"
SOURCE_LOCATION="https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git"  # GitHubリポジトリのURLに変更してください

echo "=== CodeBuildプロジェクトのセットアップを開始します ==="

# 1. ECRリポジトリの作成（存在しない場合）
echo "ECRリポジトリを確認中..."
aws ecr describe-repositories --repository-names $IMAGE_REPO_NAME --region $REGION 2>/dev/null || {
    echo "ECRリポジトリを作成中..."
    aws ecr create-repository --repository-name $IMAGE_REPO_NAME --region $REGION
}

# 2. CloudWatch Logsグループの作成
echo "CloudWatch Logsグループを作成中..."
aws logs create-log-group --log-group-name "/aws/codebuild/$PROJECT_NAME" --region $REGION 2>/dev/null || echo "ログループは既に存在します"
aws logs create-log-group --log-group-name "/ecs/transcribe-task" --region $REGION 2>/dev/null || echo "ECSログループは既に存在します"

# 3. CodeBuildサービスロールの作成
echo "CodeBuildサービスロールを作成中..."
ROLE_NAME="CodeBuildServiceRole-$PROJECT_NAME"

# 信頼関係ポリシーの作成
cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "codebuild.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# ロールの作成
aws iam create-role --role-name $ROLE_NAME --assume-role-policy-document file://trust-policy.json 2>/dev/null || echo "ロールは既に存在します"

# ポリシーのアタッチ
aws iam attach-role-policy --role-name $ROLE_NAME --policy-arn arn:aws:iam::aws:policy/AWSCodeBuildDeveloperAccess 2>/dev/null
aws iam put-role-policy --role-name $ROLE_NAME --policy-name CodeBuildCustomPolicy --policy-document file://codebuild-policy.json

# 4. CodeBuildプロジェクトの作成
echo "CodeBuildプロジェクトを作成中..."
cat > codebuild-project.json << EOF
{
  "name": "$PROJECT_NAME",
  "description": "Transcribe app build and deploy project",
  "source": {
    "type": "GITHUB",
    "location": "$SOURCE_LOCATION",
    "buildspec": "ecs/transcribe/buildspec.yml"
  },
  "artifacts": {
    "type": "NO_ARTIFACTS"
  },
  "environment": {
    "type": "LINUX_CONTAINER",
    "image": "aws/codebuild/amazonlinux2-x86_64-standard:3.0",
    "computeType": "BUILD_GENERAL1_MEDIUM",
    "privilegedMode": true,
    "environmentVariables": [
      {
        "name": "AWS_DEFAULT_REGION",
        "value": "$REGION"
      },
      {
        "name": "AWS_ACCOUNT_ID",
        "value": "$ACCOUNT_ID"
      },
      {
        "name": "IMAGE_REPO_NAME",
        "value": "$IMAGE_REPO_NAME"
      }
    ]
  },
  "serviceRole": "arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"
}
EOF

aws codebuild create-project --cli-input-json file://codebuild-project.json 2>/dev/null || {
    echo "プロジェクトは既に存在します。更新中..."
    aws codebuild update-project --cli-input-json file://codebuild-project.json
}

# 5. ビルドの実行
echo "ビルドを開始中..."
BUILD_ID=$(aws codebuild start-build --project-name $PROJECT_NAME --query 'build.id' --output text)
echo "ビルドID: $BUILD_ID"

# ビルドの進行状況を監視
echo "ビルドの進行状況を監視中..."
while true; do
    BUILD_STATUS=$(aws codebuild batch-get-builds --ids $BUILD_ID --query 'builds[0].buildStatus' --output text)
    echo "現在のステータス: $BUILD_STATUS"
    
    if [ "$BUILD_STATUS" = "SUCCEEDED" ]; then
        echo "✅ ビルドが正常に完了しました！"
        break
    elif [ "$BUILD_STATUS" = "FAILED" ] || [ "$BUILD_STATUS" = "FAULT" ] || [ "$BUILD_STATUS" = "STOPPED" ] || [ "$BUILD_STATUS" = "TIMED_OUT" ]; then
        echo "❌ ビルドが失敗しました。ステータス: $BUILD_STATUS"
        echo "詳細はCodeBuildコンソールで確認してください: https://console.aws.amazon.com/codesuite/codebuild/projects/$PROJECT_NAME/history"
        exit 1
    fi
    
    sleep 30
done

# クリーンアップ
rm -f trust-policy.json codebuild-project.json

echo "=== デプロイが完了しました ==="
echo "ECRリポジトリ: $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$IMAGE_REPO_NAME"
echo "ECSタスク定義: transcribe-task"
echo "CodeBuildプロジェクト: $PROJECT_NAME" 