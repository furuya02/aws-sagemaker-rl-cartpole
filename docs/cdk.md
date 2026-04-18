# CDK について — 本プロジェクトの CDK 設計ノート

本プロジェクトが AWS CDK (TypeScript) でインフラを構築した際の設計判断をまとめたドキュメント。特に以下の 2 点に重点を置きます。

- **なぜ BaseStack と ModelStack の 2 スタックに分けたのか**
- **なぜ Endpoint だけ CDK 管理から外してスクリプトにしたのか**

---

## 1. なぜ AWS CDK を選んだか

IaC (Infrastructure as Code) の選択肢には CloudFormation (YAML/JSON) / Terraform / Pulumi / AWS CDK などがあります。本プロジェクトで CDK を選んだ理由:

- **AWS 純正**で新サービスへの追従が早い（SageMaker L1 Construct が揃っている）
- **プログラミング言語**で書ける（if / ループ / モジュール化 / 型が使える）
- **テンプレート量が圧倒的に少なくなる**（L2 Construct がベストプラクティスを隠してくれる）
- CDK Bootstrap を 1 度実行すれば、複数プロジェクトで再利用できる

## 2. なぜ TypeScript か

Python と TypeScript が有力候補でしたが、TypeScript を採用しました。

| 観点 | TypeScript | Python |
|---|---|---|
| 静的型チェック | **◎**（IDE で補完・型エラー即検出） | △（型ヒントはあるが実行時まで検出されない） |
| CDK コミュニティの主流度 | **◎** | ○ |
| SageMaker 本体との言語分離 | **◎**（インフラ層 vs ランタイム層が明確） | △（両方 Python で書ける → 境界曖昧） |

加えて、本プロジェクトでは **`npm` / `npx` は使用しない方針** で、`pnpm` だけを使います。`cdk.json` の `app` 設定を `pnpm exec ts-node --prefer-ts-exts bin/aws-sagemaker-rl-cartpole.ts` としています。

## 3. リソースの 3 層モデル

本プロジェクトで扱う AWS リソースを、**変化頻度と課金特性** で 3 層に整理しました。

| 層 | リソース | 変化頻度 | 課金 | 管理 |
|---|---|---|---|---|
| **永続基盤** | S3 / IAM Role / IAM Policy | 稀 | ほぼゼロ | **CDK (BaseStack)** |
| **モデル成果物** | SageMaker Model / EndpointConfig | 学習のたび | ゼロ（メタデータのみ） | **CDK (ModelStack)** |
| **稼働インスタンス** | SageMaker Endpoint | 使う時だけ | **時間課金** ($0.12/h) | **スクリプト** |

この「変化頻度 × 課金特性」で層を切ったことが、CDK 設計全体の指針になっています。

## 4. BaseStack (`AwsSagemakerRlCartpoleBaseStack`)

**ファイル**: `cdk/lib/aws-sagemaker-rl-cartpole-base-stack.ts`

### 4.1 S3 バケット

```typescript
bucketName: `${PROJECT_NAME}-${bucketSuffix}`
```

- **`PROJECT_NAME`**: `aws-sagemaker-rl-cartpole` 固定
- **`bucketSuffix`**: コンテキスト `bucket_suffix` で上書き可、既定は `this.account`（AWS アカウント ID）
    - `cdk deploy -c bucket_suffix=20260419` のように任意の値に固定できる
    - ブログ用スクリーンショットでアカウント ID を露出したくない場合に利用

`autoDeleteObjects: true` を指定しているため、`cdk destroy` 時にバケット内の学習成果物も自動削除されます。

### 4.2 IAM Role

- **名前**: `aws-sagemaker-rl-cartpole-sagemaker-execution-role`
- **Managed Policy**: `AmazonSageMakerFullAccess`
- **Inline Policy**: `aws-sagemaker-rl-cartpole-sagemaker-s3-rw-policy`（バケット専用の R/W 権限）

### 4.3 CfnOutput

- `ArtifactsBucketName`
- `SageMakerExecutionRoleArn`

これらは `scripts/launch_training.py` などから CLI 引数経由で渡されます。

## 5. ModelStack (`AwsSagemakerRlCartpoleModelStack`)

**ファイル**: `cdk/lib/aws-sagemaker-rl-cartpole-model-stack.ts`

### 5.1 Cross-Stack Reference

ModelStack は BaseStack の `sageMakerExecutionRole` を **props 経由** で受け取ります:

```typescript
// bin/aws-sagemaker-rl-cartpole.ts
new AwsSagemakerRlCartpoleModelStack(app, 'AwsSagemakerRlCartpoleModelStack', {
  env,
  executionRole: baseStack.sageMakerExecutionRole,
  modelDataUrl,
});
```

CDK はこれを検出し、**CloudFormation レベルでは `Export` / `ImportValue`** に自動的に変換します。BaseStack 側に Export が増え、ModelStack の CFn テンプレートが `Fn::ImportValue` で参照する構造になります。

この仕組みにより:

- ModelStack 単独では deploy できない（= BaseStack が先に必要）
- BaseStack を destroy するには先に ModelStack を destroy する必要がある（= 依存関係が壊れない）

が CFn レベルで保証されます。

### 5.2 `model_data_url` コンテキストで条件付きインスタンス化

```typescript
const modelDataUrl = app.node.tryGetContext('model_data_url') as string | undefined;
if (modelDataUrl) {
  new AwsSagemakerRlCartpoleModelStack(app, '...', { ..., modelDataUrl });
}
```

- コンテキスト未指定 → ModelStack は app に存在しない（= BaseStack のみ）
- コンテキスト指定 → ModelStack が app に存在する

### 5.3 CfnOutput

- `CartPoleEndpointConfigName` — 起動スクリプトが `create_endpoint` API に渡す

## 6. なぜ Endpoint は CDK 管理ではなくスクリプトなのか

### 6.1 時間課金リソースの特殊性

Endpoint (`ml.m5.large`) は **起動している間 $0.12 / 時間** の課金が発生します。動作確認のたびに起動 → 確認 → 停止、を何度も繰り返したいのが実情です。

### 6.2 CDK で起停させた場合の問題

Endpoint を CfnEndpoint で定義すると:

- **起停のたびに `cdk deploy` / `cdk destroy`**（= 数分の待機 × 毎回）
- スタックの update が重い（CFn API コール、changeset 計算、rollback リスク）
- 起停コマンドと CDK の単位が噛み合わず、スクリプト層と CDK 層が混ざる

### 6.3 分離した設計

- **CDK が管理**: Model / EndpointConfig（宣言的、永続、無料）
- **スクリプトが管理**: Endpoint（命令的、起停、時間課金）
    - `scripts/start_endpoint.py` — `create_endpoint` + `endpoint_in_service` waiter
    - `scripts/stop_endpoint.py` — `delete_endpoint` + `endpoint_deleted` waiter

これにより:

- Endpoint 起停は **boto3 API を直叩き** するスクリプトだけで完結（数分 → 起動 4〜6 分 / 停止 1〜2 分）
- CDK は触らないので、**ModelStack の Model / EndpointConfig は起動中でも停止中でも同じ状態** を保てる
- 「同じ EndpointConfig を使って 2〜3 回目の再起動をする」も `start_endpoint.py` 1 本で可能

## 7. context 引数の使い分け

| 引数 | 既定値 | 用途 |
|---|---|---|
| `bucket_suffix` | `this.account` (AWS アカウント ID) | S3 バケット名のサフィックスを固定値に差し替える（ブログ用） |
| `model_data_url` | 未指定 | ModelStack の存在フラグを兼ね、`S3 URI` を受け渡す |

## 8. 運用フロー

```
[1] cdk deploy AwsSagemakerRlCartpoleBaseStack               # 永続基盤（1回）
[2] python scripts/launch_training.py ...                    # 学習（モデル成果物が S3 へ）
[3] cdk deploy AwsSagemakerRlCartpoleModelStack -c model_data_url=<URI>
                                                              # Model + EndpointConfig 登録
─── ここから 4〜6 を必要に応じて繰り返し ───
[4] python scripts/start_endpoint.py ...                     # Endpoint 起動 ← 課金開始
[5] python scripts/invoke_endpoint.py ...                    # 推論
[6] python scripts/stop_endpoint.py ...                      # Endpoint 停止 ← 課金停止
──────────────────────────────────────
[7] cdk destroy --all -c model_data_url=placeholder          # 完全撤収時のみ
```

**Endpoint の起動しっぱなしさえ避けていれば、月額コストはほぼゼロ** に保てます。

## 9. destroy 時の `placeholder` について

```bash
cdk destroy --all -c model_data_url=placeholder
```

この `placeholder` は一見不自然ですが、CDK の仕組み上必要になります。

`bin/aws-sagemaker-rl-cartpole.ts` は `model_data_url` が渡された時だけ ModelStack を instantiate します。コンテキスト未指定だと、app に ModelStack が存在せず、CDK は **どのスタックを削除すればよいかわからない** 状態になります。

destroy 時の URL の値は CFn 側のリソース削除には使われないため、**非空の任意値で OK** です。`placeholder` でも `unused` でも、当時の真の URI を覚えていればそれでも構いません。

## 10. 応用: 他のワークロードへの流用

この「**永続基盤 / モデル成果物 / 稼働インスタンス** の 3 層分離」は、SageMaker に限らず、他の AWS 推論ワークロード（Lambda 関数をスケジュールで起停するパイプライン、Fargate タスク、など）にも応用が効きます。

**変化頻度 × 課金特性 で層を切る** という考え方自体が、AWS IaC 設計の汎用的な補助線になります。
