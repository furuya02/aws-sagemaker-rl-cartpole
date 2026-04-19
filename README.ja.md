# aws-sagemaker-rl-cartpole

Amazon SageMaker で強化学習 (Gymnasium CartPole × Stable-Baselines3 PPO) を動かす一連の動作を、AWS CDK (TypeScript) を使って確認してみました。
Endpoint は意図的に CDK 管理から外し、スクリプトで起停できる構成にしています（未使用時の時間課金をゼロにするため）。

## 動作確認できたこと

- CDK で S3 / IAM / SageMaker Model / EndpointConfig をプロビジョニング
- SageMaker Training Job (PyTorch DLC, Script Mode) で PPO ポリシーを約4分でトレーニング
- 成果物 (`model.tar.gz`) が S3 に出力される
- スクリプトで EndpointConfig から Endpoint を起動
- 推論結果は最適行動を返し、5/5 エピソードで CartPole-v1 の最大報酬 (500) を達成
- スクリプトで Endpoint を停止すると時間課金がゼロに戻り、Model と EndpointConfig は残ったままなので即座に再起動できる

## ディレクトリ構成

```
.
├── cdk/          # TypeScript CDK プロジェクト (S3, IAM, Model, EndpointConfig)
├── training/     # SageMaker トレーニングコンテナのエントリポイント (Python)
├── scripts/      # ローカルスクリプト (training 起動・endpoint 起停・推論)
├── README.md     # 英語版
└── README.ja.md  # このファイル (日本語版)
```

## 前提

- Node.js 20 以上
- pnpm (本プロジェクトでは `npm` は使用しません)
- AWS CDK v2 CLI (`pnpm add -g aws-cdk`)
- Python 3.10 以上
- AWS 認証情報が設定済 (`aws configure` もしくは `.env` と環境変数)
- 対象リージョン: `ap-northeast-1`

## 1. clone と依存インストール

```bash
git clone https://github.com/<OWNER>/aws-sagemaker-rl-cartpole.git
cd aws-sagemaker-rl-cartpole

# CDK (TypeScript) 依存
cd cdk
pnpm install
cd ..

# ローカル Python スクリプト依存
python3 -m venv .venv
source .venv/bin/activate
pip install -r scripts/requirements.txt
```

## 2. 基盤リソースをデプロイ (S3 + IAM Role)

```bash
cd cdk
pnpm exec cdk bootstrap                              # 初回のみ
pnpm exec cdk deploy AwsSagemakerRlCartpoleBaseStack
cd ..
```

`AwsSagemakerRlCartpoleBaseStack` は永続的な基盤スタック (S3 + IAM のみ、
月額ほぼゼロ)。本プロジェクトは BaseStack (永続) と ModelStack
(学習のたびに作られる成果物) の 2 スタックに分かれており、モデルを
差し替えても永続リソースに触らない構造にしています。

このステップで作られるリソース名:

| リソース | デフォルト名 |
|---|---|
| S3 バケット | `aws-sagemaker-rl-cartpole-<AWS_ACCOUNT_ID>` |
| IAM ロール | `aws-sagemaker-rl-cartpole-sagemaker-execution-role` |
| IAM インラインポリシー | `aws-sagemaker-rl-cartpole-sagemaker-s3-rw-policy` |

S3 バケット名はグローバル一意のため AWS アカウント ID を含みます。
スクリーンショット等でアカウント ID を出したくない場合は、CDK コンテキスト
`bucket_suffix` で固定値に差し替えできます:

```bash
pnpm exec cdk deploy -c bucket_suffix=20260419
# → バケット名は aws-sagemaker-rl-cartpole-20260419 になる
```

出力を控えます:
- `ArtifactsBucketName`
- `SageMakerExecutionRoleArn`

## 3. Training Job を実行

```bash
python scripts/launch_training.py \
  --role-arn <SageMakerExecutionRoleArn> \
  --bucket   <ArtifactsBucketName>
```

完了時に標準出力に表示される `Model artifact S3 URI` を控えます
(例: `s3://<ArtifactsBucketName>/training-output/<job-name>/output/model.tar.gz`)。

Training Job は `model.tar.gz` の中に中間チェックポイント
(`checkpoints/cartpole_ppo_*_steps.zip`) も保存しています
（`total-timesteps/5` 環境ステップごと + 学習前の step 0 スナップショット）。
これは次のステップで使用します。

## 4. チェックポイント比較動画を録画（任意だが推奨）

学習済み `model.tar.gz` をローカルに DL して各チェックポイントをロードし、
1 エピソードずつ録画して **方策が学習ステップとともにどう改善していくか** を可視化します。
このステップは Endpoint を **使わない** ので追加の課金はゼロ。

```bash
python scripts/record_checkpoints.py \
  --model-data-url <ステップ3のS3 URI>
```

出力: `./videos/checkpoints/cp_000000-episode-0.mp4` 〜 `cp_050000-episode-0.mp4`
（チェックポイントごとに 1 本）。step 0 動画は未学習方策（即倒れ）、
step 50,000 動画は完成方策（500 ステップ直立）を示します。

## 5. Model と EndpointConfig を登録

```bash
cd cdk
pnpm exec cdk deploy AwsSagemakerRlCartpoleModelStack -c model_data_url=<ステップ3のS3 URI>
cd ..
```

`SageMaker::Model` と `SageMaker::EndpointConfig` を別スタックとして追加します
（どちらもメタデータのみで無料）。ModelStack は CloudFormation の export / import
経由で BaseStack の SageMaker 実行ロールを参照します。実際の `Endpoint`（時間
課金リソース）は **CDK では作成しません**。スクリプトで起停することで、
推論しない時間の課金をゼロにできます。

出力を控えます:
- `CartPoleEndpointConfigName`

## 6. Endpoint を起動（ここから時間課金開始）

```bash
python scripts/start_endpoint.py --endpoint-config-name <CartPoleEndpointConfigName>
```

デフォルトの Endpoint 名: `cartpole-endpoint`（`--endpoint-name` で上書き可）。

## 7. 推論を実行

```bash
python scripts/invoke_endpoint.py --endpoint-name cartpole-endpoint
```

各エピソードごとに `steps` / `reward` が表示されます (CartPole-v1 は 1 エピソード最大 500 ステップ)。

### オプション: 各エピソードを MP4 動画として録画

```bash
python scripts/invoke_endpoint.py \
  --endpoint-name cartpole-endpoint \
  --record-video
```

`./videos/cartpole-episode-*.mp4` に 1 エピソードあたり 1 本の MP4 が出力されます。
`pygame` / `moviepy` / `imageio-ffmpeg` に依存しますが、`scripts/requirements.txt`
に記載済みなので `pip install -r scripts/requirements.txt` で自動的に揃います。

## 8. Endpoint を停止（ここで時間課金停止）

```bash
python scripts/stop_endpoint.py --endpoint-name cartpole-endpoint
```

ステップ 6〜8 は何度でも繰り返せます。Model と EndpointConfig は無料で保持されます。

## 9. 完全クリーンアップ（リソースを丸ごと消す時のみ）

```bash
cd cdk
pnpm exec cdk destroy --all -c model_data_url=placeholder
cd ..
```

`-c model_data_url=placeholder` を渡すのは、CDK が destroy 時に
ModelStack をアプリグラフで認識できるようにするためです。URL の値は削除処理では
使われないので、空でなければ何でも構いません。

ModelStack 未デプロイで BaseStack だけを削除したい場合:

```bash
cd cdk
pnpm exec cdk destroy AwsSagemakerRlCartpoleBaseStack
cd ..
```

## 生成されるモデルについて

### タスク: CartPole-v1
左右に押せるカートの上に立てた棒を倒さないようバランスを取り続けるタスク。

- **観測** (float 4次元): カート位置、カート速度、棒の角度、棒の角速度
- **行動** (int 1次元): `0` = カートを左に押す、`1` = 右に押す
- **報酬**: 1ステップ棒が立ち続けるたびに `+1`
- **エピソード終了条件**: 棒の角度が ±12° を超える / カート位置が ±2.4 を超える / 500 ステップ経過
- **最大報酬**: 500（1エピソード通じて完全にバランスを保てた状態）

### アルゴリズムとネットワーク
Stable-Baselines3 `PPO` + `MlpPolicy`:

- On-policy な Actor-Critic、Clipped surrogate objective (PPO)
- デフォルトの方策・価値関数ネットワーク: 隠れ層 2 段 × 64 ユニット、`tanh` 活性化
- 5 万ステップ分の環境とのやり取りでトレーニング（`--total-timesteps` で変更可）
- CPU インスタンス 1 台 (`ml.m5.large`)、GPU 不要

### 推論の入出力
Endpoint は JSON in / JSON out:

```jsonc
// リクエスト本文
{ "observation": [0.012, -0.034, 0.001, 0.058] }

// レスポンス本文
{ "action": 1 }
```

`inference.py` は `model.predict(obs, deterministic=True)` を呼ぶので、同じ観測には常に同じ行動を返します。

### モデルアーティファクトの構造 (`model.tar.gz`)
SageMaker Training Job が S3 にアップロードするアーカイブ:

```
model.tar.gz
├── cartpole_ppo.zip   # Stable-Baselines3 PPO モデル本体 (PyTorch state + SB3 config)
└── code/
    ├── inference.py     # SageMaker model_fn / input_fn / predict_fn / output_fn
    └── requirements.txt # gymnasium, stable-baselines3
```

Endpoint 起動時に PyTorch 推論 DLC が以下を実行:

1. S3 から `model.tar.gz` を取得し `/opt/ml/model/` に展開
2. CDK の Model リソースで設定した `SAGEMAKER_PROGRAM=inference.py` と `SAGEMAKER_SUBMIT_DIRECTORY=/opt/ml/model/code` を見てエントリポイントを特定
3. `code/requirements.txt` を `pip install` して PPO を読み込めるようにする
4. 起動時に `model_fn("/opt/ml/model")` を 1 回呼び、以降の各リクエストは `input_fn` → `predict_fn` → `output_fn` の順で処理

### 動作確認した結果
デフォルトの 5 万ステップでトレーニングした場合:

| 指標 | 結果 |
|---|---|
| トレーニング時間 (Training Job) | 約 4 分（課金秒数 220 秒） |
| 評価エピソードの報酬 (seed 0〜4 の 5 試行) | **5/5 で 500 / 500 を達成** |
| Endpoint コールドスタート (`start_endpoint.py`) | 約 4〜6 分 |
| Endpoint 削除 (`stop_endpoint.py`) | 約 1〜2 分 |
| 1 リクエストあたり推論レイテンシ | 数十ミリ秒（小規模 MLP・CPU） |

## 料金目安

| リソース | インスタンス | 時間あたり | 使用時間 | 小計 |
|---|---|---:|---|---:|
| Training job | ml.m5.large × 1 | 約 $0.12 | 5〜10 分 | < $0.02 |
| Endpoint (起動中) | ml.m5.large × 1 | 約 $0.12 | start → stop | $0.12 × 時間 |
| Model + EndpointConfig (Endpoint停止中) | – | – | メタデータのみ | $0 |
| S3 / Lambda / CloudWatch | – | – | 微小 | < $0.01 |

**推論しない時は必ず `stop_endpoint.py` を、終わったら `cdk destroy` を実行してください**。

## 構成要素

| レイヤ | 使用しているもの |
|---|---|
| RL | Gymnasium `CartPole-v1`, Stable-Baselines3 `PPO` |
| Compute | SageMaker Training Job (PyTorch DLC, Script Mode) |
| Serving | SageMaker Model / EndpointConfig / Endpoint (PyTorch DLC inference) |
| Infra (TypeScript CDK) | S3 Bucket, IAM Role, `aws_sagemaker` L1 constructs |
| ローカルスクリプト (Python / boto3) | training 起動、endpoint 起停、推論クライアント |

## ライセンス

MIT License で公開しています。詳細は [LICENSE](LICENSE) を参照してください。

## コントリビューション

Pull Request は歓迎します。大きな変更の場合は、先に Issue を立てて議論してから進めてください。
