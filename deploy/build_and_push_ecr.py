#!/usr/bin/env python3
"""
ECR image build-and-push helper for Business Entity Resolution.

Builds the Docker image from the project root Dockerfile and
pushes it to Amazon ECR, ready for SageMaker Processing Jobs.

Usage:
    python deploy/build_and_push_ecr.py \
        --repo-name entity-resolution \
        --region    us-east-1 \
        [--tag      latest]
"""

import argparse
import subprocess
import boto3

def run(cmd: str, **kwargs):
    print(f"$ {cmd}")
    subprocess.run(cmd, shell=True, check=True, **kwargs)

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--repo-name", default="entity-resolution")
    p.add_argument("--region",    default="us-east-1")
    p.add_argument("--tag",       default="latest")
    return p.parse_args()

def main():
    args = parse_args()

    # Get AWS account ID
    account_id = boto3.client("sts", region_name=args.region)\
                      .get_caller_identity()["Account"]
    registry   = f"{account_id}.dkr.ecr.{args.region}.amazonaws.com"
    full_image = f"{registry}/{args.repo_name}:{args.tag}"

    # Create ECR repo (idempotent)
    ecr = boto3.client("ecr", region_name=args.region)
    try:
        ecr.create_repository(repositoryName=args.repo_name)
        print(f"[INFO] Created ECR repo: {args.repo_name}")
    except ecr.exceptions.RepositoryAlreadyExistsException:
        print(f"[INFO] ECR repo already exists: {args.repo_name}")

    # Authenticate Docker to ECR
    run(f"aws ecr get-login-password --region {args.region} "
        f"| docker login --username AWS --password-stdin {registry}")

    # Build & push
    run(f"docker build -t {full_image} .")
    run(f"docker push {full_image}")

    print(f"\n✅  Image pushed: {full_image}")
    print(f"    Use this URI in sagemaker_job.py --image flag.")

if __name__ == "__main__":
    main()
