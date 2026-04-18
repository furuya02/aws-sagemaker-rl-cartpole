"""Invoke the deployed SageMaker endpoint using Gymnasium CartPole."""
import argparse
import json

import boto3
import gymnasium as gym


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument("--episodes", type=int, default=5)
    return parser.parse_args()


def query_action(runtime_client, endpoint_name: str, observation) -> int:
    response = runtime_client.invoke_endpoint(
        EndpointName=endpoint_name,
        ContentType="application/json",
        Body=json.dumps({"observation": observation.tolist()}),
    )
    prediction: dict = json.loads(response["Body"].read().decode("utf-8"))
    return int(prediction["action"])


def main() -> None:
    args: argparse.Namespace = parse_args()
    runtime_client = boto3.client("sagemaker-runtime", region_name=args.region)
    env: gym.Env = gym.make("CartPole-v1")

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


if __name__ == "__main__":
    main()
