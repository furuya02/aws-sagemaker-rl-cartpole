"""Provision a SageMaker Endpoint from an existing EndpointConfig (billing starts here)."""
import argparse
import sys
import time

import boto3
from botocore.exceptions import ClientError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint-config-name", required=True, help="CartPoleEndpointConfigName from CDK output")
    parser.add_argument("--endpoint-name", default="cartpole-endpoint")
    parser.add_argument("--region", default="ap-northeast-1")
    return parser.parse_args()


def main() -> None:
    args: argparse.Namespace = parse_args()
    sagemaker_client = boto3.client("sagemaker", region_name=args.region)

    print(f"[start] Creating endpoint '{args.endpoint_name}' from config '{args.endpoint_config_name}'")
    try:
        sagemaker_client.create_endpoint(
            EndpointName=args.endpoint_name,
            EndpointConfigName=args.endpoint_config_name,
        )
    except ClientError as error:
        if "Cannot create already existing" in str(error):
            print(f"[start] Endpoint '{args.endpoint_name}' already exists. Reusing.")
        else:
            raise

    print("[start] Waiting for endpoint to become InService (this typically takes 4-6 minutes)...")
    started_at: float = time.time()
    waiter = sagemaker_client.get_waiter("endpoint_in_service")
    waiter.wait(EndpointName=args.endpoint_name, WaiterConfig={"Delay": 15, "MaxAttempts": 60})
    elapsed: float = time.time() - started_at
    print(f"[start] Endpoint '{args.endpoint_name}' is InService (took {elapsed:.0f}s).")
    print(f"[start] BILLING STARTED. Run scripts/stop_endpoint.py --endpoint-name {args.endpoint_name} when done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[start] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
