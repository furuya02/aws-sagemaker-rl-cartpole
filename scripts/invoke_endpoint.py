"""Invoke the deployed SageMaker endpoint using Gymnasium CartPole."""
import argparse
import json

import boto3
import gymnasium as gym
from gymnasium.wrappers import RecordVideo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument(
        "--record-video",
        action="store_true",
        help="Record each episode as MP4 under --video-dir (requires moviepy / imageio-ffmpeg).",
    )
    parser.add_argument(
        "--video-dir",
        default="./videos",
        help="Directory to save recorded videos (only used with --record-video).",
    )
    return parser.parse_args()


def query_action(runtime_client, endpoint_name: str, observation) -> int:
    response = runtime_client.invoke_endpoint(
        EndpointName=endpoint_name,
        ContentType="application/json",
        Body=json.dumps({"observation": observation.tolist()}),
    )
    prediction: dict = json.loads(response["Body"].read().decode("utf-8"))
    return int(prediction["action"])


def build_env(record_video: bool, video_dir: str) -> gym.Env:
    if record_video:
        env: gym.Env = gym.make("CartPole-v1", render_mode="rgb_array")
        env = RecordVideo(
            env,
            video_folder=video_dir,
            episode_trigger=lambda episode_index: True,
            name_prefix="cartpole",
        )
        return env
    return gym.make("CartPole-v1")


def main() -> None:
    args: argparse.Namespace = parse_args()
    runtime_client = boto3.client("sagemaker-runtime", region_name=args.region)
    env: gym.Env = build_env(args.record_video, args.video_dir)

    for episode_index in range(args.episodes):
        observation, _info = env.reset(seed=episode_index)
        total_reward: float = 0.0
        step_count: int = 0
        done: bool = False
        while not done:
            action: int = query_action(runtime_client, args.endpoint_name, observation)
            observation, reward, terminated, truncated, _info = env.step(action)
            total_reward += float(reward)
            step_count += 1
            done = terminated or truncated
        print(f"Episode {episode_index}: steps={step_count}, reward={total_reward}")

    env.close()
    if args.record_video:
        print(f"[invoke] Videos saved under {args.video_dir}/")


if __name__ == "__main__":
    main()
