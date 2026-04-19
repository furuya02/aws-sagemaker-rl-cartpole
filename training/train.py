"""SageMaker Script Mode training script: PPO on Gymnasium CartPole."""
import argparse
import os
import shutil
from pathlib import Path

import gymnasium as gym
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback


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

    model_output_dir: Path = Path(args.model_dir)
    model_output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir: Path = model_output_dir / "checkpoints"
    checkpoint_dir.mkdir(exist_ok=True)

    # Save the untrained (step 0) model so that the very first video shows
    # the random baseline alongside later checkpoints.
    initial_checkpoint_path: Path = checkpoint_dir / "cartpole_ppo_0_steps.zip"
    ppo_model.save(str(initial_checkpoint_path))
    print(f"[train] Saved initial (untrained) checkpoint to {initial_checkpoint_path}")

    # Save a checkpoint every total_timesteps/5 env steps -> roughly 5 intermediate saves.
    save_freq: int = max(1, args.total_timesteps // 5)
    checkpoint_cb: CheckpointCallback = CheckpointCallback(
        save_freq=save_freq,
        save_path=str(checkpoint_dir),
        name_prefix="cartpole_ppo",
    )

    ppo_model.learn(total_timesteps=args.total_timesteps, callback=checkpoint_cb)

    model_artifact_path: Path = model_output_dir / "cartpole_ppo.zip"
    ppo_model.save(str(model_artifact_path))
    print(f"[train] Saved final model to {model_artifact_path}")

    source_dir: Path = Path(__file__).parent
    inference_code_dir: Path = model_output_dir / "code"
    inference_code_dir.mkdir(exist_ok=True)
    shutil.copy(source_dir / "inference.py", inference_code_dir / "inference.py")
    shutil.copy(source_dir / "requirements.txt", inference_code_dir / "requirements.txt")
    print(f"[train] Copied inference code to {inference_code_dir}")


if __name__ == "__main__":
    main()
