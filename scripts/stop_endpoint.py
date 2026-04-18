"""Delete a SageMaker Endpoint to stop hourly billing (EndpointConfig is preserved for re-start)."""
import argparse
import sys
import time

import boto3
from botocore.exceptions import ClientError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint-name", default="cartpole-endpoint")
    parser.add_argument("--region", default="ap-northeast-1")
    return parser.parse_args()


def main() -> None:
    args: argparse.Namespace = parse_args()
    sagemaker_client = boto3.client("sagemaker", region_name=args.region)

    print(f"[stop] Deleting endpoint '{args.endpoint_name}'")
    try:
        sagemaker_client.delete_endpoint(EndpointName=args.endpoint_name)
    except ClientError as error:
        if "Could not find endpoint" in str(error):
            print(f"[stop] Endpoint '{args.endpoint_name}' does not exist. Already stopped.")
            return
        raise

    print("[stop] Waiting for endpoint to be fully deleted (typically 1-2 minutes)...")
    started_at: float = time.time()
    waiter = sagemaker_client.get_waiter("endpoint_deleted")
    waiter.wait(EndpointName=args.endpoint_name, WaiterConfig={"Delay": 10, "MaxAttempts": 30})
    elapsed: float = time.time() - started_at
    print(f"[stop] Endpoint '{args.endpoint_name}' deleted (took {elapsed:.0f}s).")
    print("[stop] BILLING STOPPED.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[stop] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
