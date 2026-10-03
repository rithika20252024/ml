#!/usr/bin/env python3
"""
AWS SageMaker Processing Job launcher for Business Entity Resolution Pipeline.

This script submits a SageMaker Processing Job that:
1. Reads the raw dataset from S3
2. Runs the full entity resolution pipeline inside a container
3. Writes output TSVs back to S3

Usage:
    python deploy/sagemaker_job.py \
        --s3-input  s3://your-bucket/data/ \
        --s3-output s3://your-bucket/output/ \
        --role      arn:aws:iam::123456789012:role/SageMakerRole \
        [--instance ml.m5.4xlarge] \
        [--image    123456789012.dkr.ecr.us-east-1.amazonaws.com/entity-resolution:latest]
"""

import argparse
import boto3
import sagemaker
from sagemaker.processing import ScriptProcessor, ProcessingInput, ProcessingOutput

# ──────────────────────────────────────────────
# Argument parsing
# ──────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="Launch SageMaker Processing Job")
    p.add_argument("--s3-input",  required=True, help="S3 URI for input dataset folder")
    p.add_argument("--s3-output", required=True, help="S3 URI for output folder")
    p.add_argument("--role",      required=True, help="IAM role ARN for SageMaker")
    p.add_argument("--region",    default="us-east-1")
    p.add_argument("--instance",  default="ml.m5.4xlarge",
                   help="SageMaker instance type (default: ml.m5.4xlarge)")
    p.add_argument("--image",     default=None,
                   help="ECR image URI. If omitted, a pre-built sklearn image is used.")
    p.add_argument("--job-name",  default="entity-resolution-job",
                   help="SageMaker job name prefix")
    return p.parse_args()


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    args = parse_args()

    boto_session = boto3.Session(region_name=args.region)
    sm_session   = sagemaker.Session(boto_session=boto_session)

    # Use a provided ECR image, or fall back to SageMaker's managed sklearn container
    if args.image:
        image_uri = args.image
    else:
        image_uri = sagemaker.image_uris.retrieve(
            framework="sklearn",
            region=args.region,
            version="1.2-1",
            image_scope="training",
        )
        print(f"[INFO] Using managed sklearn image: {image_uri}")

    processor = ScriptProcessor(
        image_uri=image_uri,
        command=["python3"],
        instance_type=args.instance,
        instance_count=1,
        role=args.role,
        sagemaker_session=sm_session,
        base_job_name=args.job_name,
        max_runtime_in_seconds=7200,   # 2-hour hard limit
    )

    processor.run(
        code="code/business_entity_resolution/src/run_pipeline.py",
        inputs=[
            ProcessingInput(
                source=args.s3_input,
                destination="/opt/ml/processing/input",
                input_name="dataset",
            )
        ],
        outputs=[
            ProcessingOutput(
                source="/opt/ml/processing/output",
                destination=args.s3_output,
                output_name="results",
            )
        ],
        arguments=["--input-dir",  "/opt/ml/processing/input",
                   "--output-dir", "/opt/ml/processing/output"],
        wait=True,
        logs=True,
    )

    print(f"\n✅  Job complete. Results written to: {args.s3_output}")


if __name__ == "__main__":
    main()
