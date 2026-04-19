"""Record MP4 videos from each PPO checkpoint to visualize training progression."""
import argparse
import re
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import boto3
import gymnasium as gym
from gymnasium.wrappers import RecordVideo
from stable_baselines3 import PPO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-data-url",
        required=True,
        help="S3 URI to model.tar.gz produced by a Training Job (e.g. s3://bucket/.../model.tar.gz)",
    )
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument(
        "--video-dir",
        default="./videos/checkpoints",
        help="Directory to save recorded videos.",
    )
    parser.add_argument(
        "--episode-seed",
        type=int,
        default=0,
        help="Fixed seed so every checkpoint runs the same initial state (fair comparison).",
    )
    return parser.parse_args()


def download_and_extract(s3_uri: str, region: str, dest_dir: Path) -> None:
    parsed = urlparse(s3_uri)
    bucket: str = parsed.netloc
    key: str = parsed.path.lstrip("/")
    s3 = boto3.client("s3", region_name=region)
    tar_path: Path = dest_dir / "model.tar.gz"
    print(f"[record] Downloading s3://{bucket}/{key}")
    s3.download_file(bucket, key, str(tar_path))
    print(f"[record] Extracting to {dest_dir}")
    with tarfile.open(tar_path) as tar:
        tar.extractall(path=dest_dir)


def find_checkpoints(model_dir: Path) -> list[tuple[int, Path]]:
    pattern = re.compile(r"cartpole_ppo_(\d+)_steps\.zip")
    checkpoints: list[tuple[int, Path]] = []
    checkpoint_dir: Path = model_dir / "checkpoints"
    if not checkpoint_dir.is_dir():
        return checkpoints
    for path in checkpoint_dir.glob("cartpole_ppo_*_steps.zip"):
        match = pattern.match(path.name)
        if match:
            checkpoints.append((int(match.group(1)), path))
    return sorted(checkpoints)


def record_one(checkpoint_path: Path, steps: int, video_dir: Path, seed: int) -> tuple[int, float]:
    env: gym.Env = gym.make("CartPole-v1", render_mode="rgb_array")
    env = RecordVideo(
        env,
        video_folder=str(video_dir),
        episode_trigger=lambda episode_index: True,
        name_prefix=f"cp_{steps:06d}",
    )
    model = PPO.load(str(checkpoint_path))
    observation, _info = env.reset(seed=seed)
    total_reward: float = 0.0
    step_count: int = 0
    done: bool = False
    while not done:
        action, _states = model.predict(observation, deterministic=True)
        observation, reward, terminated, truncated, _info = env.step(action)
        total_reward += float(reward)
        step_count += 1
        done = terminated or truncated
    env.close()
    return step_count, total_reward


def main() -> None:
    args: argparse.Namespace = parse_args()
    video_dir: Path = Path(args.video_dir)
    video_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path: Path = Path(tmp)
        download_and_extract(args.model_data_url, args.region, tmp_path)

        checkpoints = find_checkpoints(tmp_path)
        if not checkpoints:
            raise SystemExit(
                "[record] No checkpoints found in model.tar.gz. "
                "Re-run training with CheckpointCallback enabled (training/train.py)."
            )

        print(f"[record] Found {len(checkpoints)} checkpoints at steps: "
              f"{[steps for steps, _ in checkpoints]}")
        for steps, checkpoint_path in checkpoints:
            print(f"[record] step={steps:>6} -> ", end="", flush=True)
            step_count, reward = record_one(checkpoint_path, steps, video_dir, args.episode_seed)
            print(f"episode_steps={step_count}, reward={reward}")

    print(f"[record] Videos saved under {video_dir}/")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[record] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
