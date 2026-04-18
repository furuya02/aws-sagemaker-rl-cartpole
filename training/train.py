"""SageMaker Script Mode training script: PPO on Gymnasium CartPole."""
import argparse
import os
import shutil
from pathlib import Path

import gymnasium as gym
from stable_baselines3 import PPO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--total-timesteps", type=int, default=50_000)
    parser.add_argument("--env-id", type=str, default="CartPole-v1")
    parser.add_argument(
        "--model-dir",
        type=str,
        default=os.environ.get("SM_MODEL_DIR", "./model"),
    )
    return parser.parse_args()


def main() -> None:
    args: argparse.Namespace = parse_args()

    training_env: gym.Env = gym.make(args.env_id)
    ppo_model: PPO = PPO("MlpPolicy", training_env, verbose=1)
    ppo_model.learn(total_timesteps=args.total_timesteps)

    model_output_dir: Path = Path(args.model_dir)
    model_output_dir.mkdir(parents=True, exist_ok=True)
    model_artifact_path: Path = model_output_dir / "cartpole_ppo.zip"
    ppo_model.save(str(model_artifact_path))
    print(f"[train] Saved model to {model_artifact_path}")

    source_dir: Path = Path(__file__).parent
    inference_code_dir: Path = model_output_dir / "code"
    inference_code_dir.mkdir(exist_ok=True)
    shutil.copy(source_dir / "inference.py", inference_code_dir / "inference.py")
    shutil.copy(source_dir / "requirements.txt", inference_code_dir / "requirements.txt")
    print(f"[train] Copied inference code to {inference_code_dir}")


if __name__ == "__main__":
    main()
