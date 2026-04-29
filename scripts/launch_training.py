"""Launch a SageMaker Training Job for CartPole PPO."""
import argparse
from pathlib import Path

import boto3
import sagemaker
from sagemaker.pytorch import PyTorch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role-arn", required=True, help="SageMakerExecutionRoleArn from CDK output")
    parser.add_argument("--bucket", required=True, help="ArtifactsBucketName from CDK output")
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument("--total-timesteps", type=int, default=30_000)
    parser.add_argument("--instance-type", default="ml.m5.large")
    return parser.parse_args()


def main() -> None:
    args: argparse.Namespace = parse_args()

    boto_session: boto3.Session = boto3.Session(region_name=args.region)
    sm_session: sagemaker.Session = sagemaker.Session(boto_session=boto_session)

    source_dir: str = str((Path(__file__).parent.parent / "training").resolve())

    pytorch_estimator: PyTorch = PyTorch(
        entry_point="train.py",
        source_dir=source_dir,
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
    print("Training job name:", pytorch_estimator.latest_training_job.name)
    print("Model artifact S3 URI:", pytorch_estimator.model_data)


if __name__ == "__main__":
    main()
