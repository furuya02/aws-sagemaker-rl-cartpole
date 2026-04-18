# スクリプトについて — `scripts/` 配下の実行スクリプト解説

`aws-sagemaker-rl-cartpole/scripts/` には、**CDK が作らない部分** を担う 4 本の Python スクリプトを置いています。いずれも `boto3` / `sagemaker` (v2) / `gymnasium` だけで動く薄いユーティリティで、**「SageMaker で何が起きているかが 1 ファイル 30〜50 行で追える」** ことを優先した作りです。

## 1. 概要

4 本のスクリプトは、本プロジェクトの運用ループを形作ります。

| スクリプト | 役割 | 時間課金 |
|---|---|:---:|
| [`launch_training.py`](#launch_trainingpy) | SageMaker Training Job を起動して PPO を学習させる | 起動中のみ |
| [`start_endpoint.py`](#start_endpointpy) | EndpointConfig から Endpoint を作成（InService 待機） | **開始** |
| [`invoke_endpoint.py`](#invoke_endpointpy) | CartPole を 5 エピソード走らせて Endpoint で行動決定 | 起動中のみ |
| [`stop_endpoint.py`](#stop_endpointpy) | Endpoint を削除して課金を止める | **停止** |

CDK 側 (`BaseStack`, `ModelStack`) が宣言的に管理する **永続的なリソース / メタデータ** に対し、スクリプト側は **命令的でライフサイクルの短いもの**（Training Job の起動 / Endpoint の起停 / 推論コール）を受け持っています。

## 2. 全体の実行フロー

```
CDK:    cdk deploy BaseStack
  ↓
Script: launch_training.py      (Training Job 実行、約 4 分)
  ↓
CDK:    cdk deploy ModelStack -c model_data_url=<URI>
  ↓
Script: start_endpoint.py       (Endpoint 起動、約 4〜6 分)  ← 課金開始
  ↓
Script: invoke_endpoint.py      (推論 × 5 エピソード)
  ↓
Script: stop_endpoint.py        (Endpoint 削除、約 1〜2 分)  ← 課金停止
```

`start_endpoint.py` 〜 `stop_endpoint.py` のサイクルは何度でも繰り返し可能で、Model / EndpointConfig は残り続けます。

## 3. 依存パッケージ (`requirements.txt`)

```
boto3>=1.34
sagemaker>=2.220,<3.0
gymnasium==0.29.1
```

- **`boto3`**: Endpoint の起停 / 推論コール（`sagemaker` / `sagemaker-runtime` クライアント）
- **`sagemaker`**: Training Job 起動のみで使用（**v2 系固定**。v3 は 2026 年 4 月時点で `Development Status :: 3 - Alpha` かつ `sagemaker.pytorch` Estimator を提供しないため）
- **`gymnasium`**: `invoke_endpoint.py` がローカルで CartPole-v1 環境を回すため

## 4. <a id="launch_trainingpy"></a> `launch_training.py` — Training Job 起動

### 役割
SageMaker Python SDK v2 の `sagemaker.pytorch.PyTorch` Estimator で Training Job を起動し、完了まで待機する。**完了時に `Model artifact S3 URI` を stdout に出す**（次の `cdk deploy ModelStack -c model_data_url=<URI>` に渡すため）。

### 使用例
```bash
python scripts/launch_training.py \
  --role-arn <SageMakerExecutionRoleArn> \
  --bucket   <ArtifactsBucketName> \
  --total-timesteps 50000
```

### 引数
| 引数 | 必須 | 既定 | 意味 |
|---|:---:|---|---|
| `--role-arn` | ✅ | - | BaseStack CfnOutput の `SageMakerExecutionRoleArn` |
| `--bucket` | ✅ | - | BaseStack CfnOutput の `ArtifactsBucketName`（`s3://<bucket>/training-output` に成果物が出る） |
| `--region` | - | `ap-northeast-1` | 対象リージョン |
| `--total-timesteps` | - | `50000` | PPO が環境とやり取りする総ステップ数 |
| `--instance-type` | - | `ml.m5.large` | Training Job のインスタンス |

### 中身

```python
pytorch_estimator = PyTorch(
    entry_point="train.py",
    source_dir=str((Path(__file__).parent.parent / "training").resolve()),
    role=args.role_arn,
    framework_version="2.1",
    py_version="py310",
    instance_type=args.instance_type,
    instance_count=1,
    output_path=f"s3://{args.bucket}/training-output",
    hyperparameters={"total-timesteps": args.total_timesteps},
    sagemaker_session=sm_session,
)
pytorch_estimator.fit(wait=True)
```

`source_dir=../training` で `training/` ディレクトリ全体（`train.py`, `inference.py`, `requirements.txt`）をアップロードします。Script Mode で `entry_point="train.py"` が実行され、`inference.py` は `train.py` が `model_dir/code/` に同梱することで後段の Endpoint が読める状態になります。

## 5. <a id="start_endpointpy"></a> `start_endpoint.py` — Endpoint 起動

### 役割
CDK の ModelStack が作った EndpointConfig を元に、`boto3.client("sagemaker").create_endpoint()` を呼んで Endpoint を立てる。**このスクリプトが呼ばれた瞬間から時間課金が始まる**。

### 使用例
```bash
python scripts/start_endpoint.py --endpoint-config-name <CartPoleEndpointConfigName>
```

### 引数
| 引数 | 必須 | 既定 | 意味 |
|---|:---:|---|---|
| `--endpoint-config-name` | ✅ | - | ModelStack CfnOutput の `CartPoleEndpointConfigName` |
| `--endpoint-name` | - | `cartpole-endpoint` | 作る Endpoint の名前 |
| `--region` | - | `ap-northeast-1` | 対象リージョン |

### 中身

```python
sagemaker_client.create_endpoint(
    EndpointName=args.endpoint_name,
    EndpointConfigName=args.endpoint_config_name,
)
waiter = sagemaker_client.get_waiter("endpoint_in_service")
waiter.wait(EndpointName=args.endpoint_name,
            WaiterConfig={"Delay": 15, "MaxAttempts": 60})
```

- `endpoint_in_service` waiter で **最大 15 分**（15 秒 × 60 回）待機
- 同名 Endpoint がすでに存在していれば `ClientError` を握り潰して再利用（冪等性）

## 6. <a id="invoke_endpointpy"></a> `invoke_endpoint.py` — 推論実行

### 役割
ローカルで Gymnasium `CartPole-v1` を走らせつつ、各ステップの行動決定を Endpoint に問い合わせる。**Endpoint が学習済みモデルとして期待通り働いているかの動作確認**。

### 使用例
```bash
python scripts/invoke_endpoint.py --endpoint-name cartpole-endpoint
```

### 引数
| 引数 | 必須 | 既定 | 意味 |
|---|:---:|---|---|
| `--endpoint-name` | ✅ | - | 起動済み Endpoint 名 |
| `--region` | - | `ap-northeast-1` | 対象リージョン |
| `--episodes` | - | `5` | 試行するエピソード数 |

### 中身

```python
response = runtime_client.invoke_endpoint(
    EndpointName=endpoint_name,
    ContentType="application/json",
    Body=json.dumps({"observation": observation.tolist()}),
)
prediction = json.loads(response["Body"].read().decode("utf-8"))
action = int(prediction["action"])
```

1 リクエストあたりの往復レイテンシは数十 ms 程度。学習に成功していれば **5 エピソード全てで `steps=500 / reward=500.0`**（CartPole-v1 の最大値）が出ます。

出力例:
```
Episode 0: steps=500, reward=500.0
Episode 1: steps=500, reward=500.0
Episode 2: steps=500, reward=500.0
Episode 3: steps=500, reward=500.0
Episode 4: steps=500, reward=500.0
```

## 7. <a id="stop_endpointpy"></a> `stop_endpoint.py` — Endpoint 削除

### 役割
`delete_endpoint` を呼んで Endpoint を削除し、**時間課金を止める**。Model と EndpointConfig は残るため、後で再び `start_endpoint.py` を打てば同じ構成で再起動できる。

### 使用例
```bash
python scripts/stop_endpoint.py --endpoint-name cartpole-endpoint
```

### 引数
| 引数 | 必須 | 既定 | 意味 |
|---|:---:|---|---|
| `--endpoint-name` | - | `cartpole-endpoint` | 削除対象の Endpoint 名 |
| `--region` | - | `ap-northeast-1` | 対象リージョン |

### 中身

```python
sagemaker_client.delete_endpoint(EndpointName=args.endpoint_name)
waiter = sagemaker_client.get_waiter("endpoint_deleted")
waiter.wait(EndpointName=args.endpoint_name,
            WaiterConfig={"Delay": 10, "MaxAttempts": 30})
```

- `endpoint_deleted` waiter で **最大 5 分**（10 秒 × 30 回）待機
- 存在しない Endpoint に対しては `Could not find endpoint` を握り潰して即 return（冪等性）

## 8. 設計上のポイント

### 8.1 SDK の使い分け
- **Training Job** のみ `sagemaker` Python SDK（`PyTorch` Estimator で `source_dir` のアップロード〜Training Job 作成〜待機を一括処理してくれるため）
- **Endpoint の起停・推論** は `boto3` 直叩き（`sagemaker` / `sagemaker-runtime` クライアント）
    - 起停は API が単純なので SDK のラッパーが不要
    - 推論は `sagemaker-runtime` の方が薄くて軽い

### 8.2 冪等性の担保
起停系の 2 本（`start_endpoint.py` / `stop_endpoint.py`）は、**「同名リソースが既に存在 / 存在しない」** を `ClientError` の文字列マッチで握り潰すことで、何度叩いても安全に動くようにしています。自動化パイプラインに組み込みやすくするため。

### 8.3 waiter で同期化
起停の両方で boto3 の `get_waiter` を使い、**InService / 削除完了までブロック** します。スクリプトが exit した時点で状態が確定しているので、シェルスクリプトで順次呼び出しても問題ない。

### 8.4 コストに関わる副作用を標準出力で明示
- `start_endpoint.py` 終了時: `BILLING STARTED.` を出力
- `stop_endpoint.py` 終了時: `BILLING STOPPED.` を出力

CI や cron 等から叩くときに、ログ grep で課金状態を追跡しやすくするため。

## 9. まとめ

`scripts/` 配下の 4 本は、CDK が扱わないもの（Training Job / Endpoint 起停 / 推論コール）だけを最小限の boto3 / sagemaker SDK で書いた薄いラッパーです。**宣言的に管理したい領域は CDK、命令的・頻繁に起停したい領域はスクリプト** という役割分担を素直にコードで表現したものになっています。
