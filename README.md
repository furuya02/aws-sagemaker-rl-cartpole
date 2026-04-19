# aws-sagemaker-rl-cartpole

Tried running a Reinforcement Learning workload (Gymnasium CartPole × Stable-Baselines3 PPO)
on Amazon SageMaker, with all infrastructure provisioned by AWS CDK (TypeScript).
Endpoint provisioning was deliberately split out of CDK so it can be started/stopped
on demand to keep idle hourly cost at zero.

## What was confirmed

- CDK provisions S3 + IAM + SageMaker Model + EndpointConfig
- A SageMaker Training Job (PyTorch DLC, Script Mode) trains a PPO policy in ~4 minutes
- The trained model artifact (`model.tar.gz`) is published to S3
- A separate script provisions the SageMaker Endpoint from the EndpointConfig
- Inference returns optimal actions: 5 of 5 episodes reached the CartPole-v1 max reward (500)
- Stopping the Endpoint via script returns the account to zero hourly billing while
  Model and EndpointConfig stay in place for an instant restart

## Directory layout

```
.
├── cdk/          # TypeScript CDK project (S3, IAM, Model, EndpointConfig)
├── training/     # SageMaker training container entry point (Python)
├── scripts/      # Local utility scripts (launch training, start/stop endpoint, invoke)
├── README.md     # This file (English)
└── README.ja.md  # Japanese version
```

## Prerequisites

- Node.js 20+
- pnpm (`npm` is not used in this project)
- AWS CDK v2 CLI (`pnpm add -g aws-cdk`)
- Python 3.10+
- AWS credentials configured (`aws configure` or `.env` with env vars)
- Target region: `ap-northeast-1`

## 1. Clone and install

```bash
git clone https://github.com/<OWNER>/aws-sagemaker-rl-cartpole.git
cd aws-sagemaker-rl-cartpole

# CDK (TypeScript) dependencies
cd cdk
pnpm install
cd ..

# Local Python script dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r scripts/requirements.txt
```

## 2. Deploy base infrastructure (S3 + IAM role)

```bash
cd cdk
pnpm exec cdk bootstrap                              # first time only
pnpm exec cdk deploy AwsSagemakerRlCartpoleBaseStack
cd ..
```

`AwsSagemakerRlCartpoleBaseStack` is the permanent-infrastructure stack
(S3 + IAM only; near-zero monthly cost). The project is split into two stacks
— BaseStack (permanent) and ModelStack (per-training artifact) — so that
updating a trained model never touches the permanent resources.

Resource names produced by this step:

| Resource | Default name |
|---|---|
| S3 bucket | `aws-sagemaker-rl-cartpole-<AWS_ACCOUNT_ID>` |
| IAM role | `aws-sagemaker-rl-cartpole-sagemaker-execution-role` |
| IAM inline policy | `aws-sagemaker-rl-cartpole-sagemaker-s3-rw-policy` |

The S3 bucket name uses your AWS account ID for global uniqueness.
To use a fixed suffix instead (e.g. for screenshots that should not expose
the account ID), pass `bucket_suffix` as a CDK context value:

```bash
pnpm exec cdk deploy -c bucket_suffix=20260419
# → bucket name becomes aws-sagemaker-rl-cartpole-20260419
```

Outputs to record:
- `ArtifactsBucketName`
- `SageMakerExecutionRoleArn`

## 3. Run a training job

```bash
python scripts/launch_training.py \
  --role-arn <SageMakerExecutionRoleArn> \
  --bucket   <ArtifactsBucketName>
```

On completion, record the `Model artifact S3 URI` printed to stdout
(e.g. `s3://<ArtifactsBucketName>/training-output/<job-name>/output/model.tar.gz`).

## 4. Register Model and EndpointConfig

```bash
cd cdk
pnpm exec cdk deploy AwsSagemakerRlCartpoleModelStack -c model_data_url=<s3 URI from step 3>
cd ..
```

This deploys a separate stack that adds `SageMaker::Model` and `SageMaker::EndpointConfig`
(both free metadata). ModelStack references the SageMaker execution role from
BaseStack via a CloudFormation export/import. The actual `Endpoint` is **not**
created here — it is started/stopped by scripts so hourly billing can be paused
when inference is not in use.

Output to record:
- `CartPoleEndpointConfigName`

## 5. Start the endpoint (hourly billing starts here)

```bash
python scripts/start_endpoint.py --endpoint-config-name <CartPoleEndpointConfigName>
```

Default endpoint name: `cartpole-endpoint`. Override with `--endpoint-name`.

## 6. Run inference

```bash
python scripts/invoke_endpoint.py --endpoint-name cartpole-endpoint
```

Each episode prints `steps` / `reward` (CartPole-v1 caps at 500 steps per episode).

### Optional: record MP4 videos of each episode

```bash
python scripts/invoke_endpoint.py \
  --endpoint-name cartpole-endpoint \
  --record-video
```

Saves one MP4 per episode to `./videos/cartpole-episode-*.mp4`.
Requires `pygame` / `moviepy` / `imageio-ffmpeg` (already listed in
`scripts/requirements.txt`, so `pip install -r scripts/requirements.txt`
pulls them in automatically).

## 7. Stop the endpoint (hourly billing stops here)

```bash
python scripts/stop_endpoint.py --endpoint-name cartpole-endpoint
```

Steps 5–7 can be repeated anytime — Model and EndpointConfig stay in place for free.

## 8. Full clean up (when finished for good)

```bash
cd cdk
pnpm exec cdk destroy --all -c model_data_url=placeholder
cd ..
```

The `-c model_data_url=placeholder` is required so CDK can see ModelStack in
the app graph during destroy. Any non-empty value works — the URL isn't
actually used for deletion.

To remove only BaseStack (when ModelStack is not deployed):

```bash
cd cdk
pnpm exec cdk destroy AwsSagemakerRlCartpoleBaseStack
cd ..
```

## About the generated model

### Task: CartPole-v1
The agent controls a cart that can be pushed left or right, with a pole balanced on top.
The goal is to keep the pole upright as long as possible.

- **Observation** (4 floats): cart position, cart velocity, pole angle, pole angular velocity
- **Action** (1 int): `0` = push cart left, `1` = push cart right
- **Reward**: `+1` per simulation step the pole stays upright
- **Episode terminates**: pole tilts beyond ±12°, cart drifts beyond ±2.4, or step 500 reached
- **Maximum possible reward**: 500 (perfectly balanced for the full episode)

### Algorithm and network
Stable-Baselines3 `PPO` with `MlpPolicy`:

- On-policy actor-critic, clipped surrogate objective (PPO)
- Default policy & value networks: 2 hidden layers × 64 units each, `tanh` activation
- Trained for 50,000 environment steps (override with `--total-timesteps`)
- Single CPU instance (`ml.m5.large`); no GPU required

### Inference contract
The endpoint expects JSON in / JSON out:

```jsonc
// Request body
{ "observation": [0.012, -0.034, 0.001, 0.058] }

// Response body
{ "action": 1 }
```

`inference.py` calls `model.predict(obs, deterministic=True)`, so the same observation
always returns the same action.

### Model artifact layout (`model.tar.gz`)
The SageMaker training job uploads a single archive to S3:

```
model.tar.gz
├── cartpole_ppo.zip   # Stable-Baselines3 PPO model archive (PyTorch state + SB3 config)
└── code/
    ├── inference.py     # SageMaker model_fn / input_fn / predict_fn / output_fn
    └── requirements.txt # gymnasium, stable-baselines3
```

When the endpoint starts, the PyTorch inference DLC:

1. Downloads `model.tar.gz` from S3 and extracts it to `/opt/ml/model/`
2. Reads `SAGEMAKER_PROGRAM=inference.py` + `SAGEMAKER_SUBMIT_DIRECTORY=/opt/ml/model/code`
   (set by the CDK `Model` resource) to locate the entry point
3. `pip install`s `code/requirements.txt` so PPO can be loaded
4. Calls `model_fn("/opt/ml/model")` once at startup, then routes each request through
   `input_fn` → `predict_fn` → `output_fn`

### Verified behavior
With the default 50,000 training steps:

| Metric | Result |
|---|---|
| Training time (Training Job) | ~4 minutes (220 billable seconds) |
| Reward in evaluation (5 episodes, seeds 0–4) | **500 / 500 in every episode** |
| Endpoint cold start (`start_endpoint.py`) | 4–6 minutes |
| Endpoint deletion (`stop_endpoint.py`) | 1–2 minutes |
| Per-request inference latency | tens of ms (small MLP, CPU) |

## Cost estimate

| Resource | Instance | Hourly | Usage | Subtotal |
|---|---|---:|---|---:|
| Training job | ml.m5.large × 1 | ~$0.12 | 5–10 min | < $0.02 |
| Endpoint (started) | ml.m5.large × 1 | ~$0.12 | start → stop | $0.12 × hours |
| Model + EndpointConfig (endpoint stopped) | – | – | metadata only | $0 |
| S3 / Lambda / CloudWatch | – | – | minimal | < $0.01 |

Always run `stop_endpoint.py` when not actively using inference,
and `cdk destroy` when finished.

## Components

| Layer | Component |
|---|---|
| RL | Gymnasium `CartPole-v1`, Stable-Baselines3 `PPO` |
| Compute | SageMaker Training Job (PyTorch DLC, Script Mode) |
| Serving | SageMaker Model / EndpointConfig / Endpoint (PyTorch DLC inference) |
| Infra (TypeScript CDK) | S3 Bucket, IAM Role, `aws_sagemaker` L1 constructs |
| Local scripts (Python / boto3) | training launcher, endpoint start/stop, inference client |

## License

Released under the MIT License. See [LICENSE](LICENSE) for details.

## Contributing

Pull requests are welcome. For substantial changes, please open an issue first to discuss what you would like to change.
