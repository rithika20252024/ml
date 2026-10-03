# AWS SageMaker & Cloud Deployment Guide
## Business Entity Resolution Pipeline

---

## Table of Contents
1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Project Structure](#3-project-structure)
4. [Quick Start (Local)](#4-quick-start-local)
5. [S3 Data Setup](#5-s3-data-setup)
6. [ECR Image Build & Push](#6-ecr-image-build--push)
7. [SageMaker Processing Job](#7-sagemaker-processing-job)
8. [SageMaker Pipeline (Orchestrated)](#8-sagemaker-pipeline-orchestrated)
9. [Cost Estimation](#9-cost-estimation)
10. [IAM Permissions](#10-iam-permissions)
11. [Monitoring & Logs](#11-monitoring--logs)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        AWS Cloud                                │
│                                                                 │
│  ┌──────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │    S3    │───▶│  SageMaker       │───▶│       S3         │  │
│  │ (Input)  │    │  Processing Job  │    │   (Output TSVs)  │  │
│  │          │    │                  │    │                  │  │
│  │ dataset/ │    │  ml.m5.4xlarge   │    │ matching_results │  │
│  │  ├─s1    │    │  (32 vCPU,64GB)  │    │ candidate_pairs  │  │
│  │  ├─s2    │    │                  │    │                  │  │
│  │  └─s3    │    │  Docker Container│    └──────────────────┘  │
│  └──────────┘    │  ┌────────────┐  │                          │
│                  │  │resolver.py │  │    ┌──────────────────┐  │
│  ┌──────────┐    │  │run_pipeline│  │    │   CloudWatch     │  │
│  │   ECR    │───▶│  └────────────┘  │───▶│     Logs         │  │
│  │  (Image) │    └──────────────────┘    └──────────────────┘  │
│  └──────────┘                                                   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              IAM Role: SageMakerExecutionRole             │  │
│  │    (AmazonSageMakerFullAccess + S3 Read/Write + ECR)      │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Data flow:**
1. Raw dataset CSVs uploaded to **S3 (Input)**
2. SageMaker spins up a managed `ml.m5.4xlarge` instance
3. Container pulls from **ECR**, mounts S3 input → `/opt/ml/processing/input`
4. Pipeline runs `resolver.py` across US / India / France partitions
5. Output TSVs written to `/opt/ml/processing/output` → synced back to **S3 (Output)**
6. All logs streamed to **CloudWatch Logs**

---

## 2. Prerequisites

### Local tools required
| Tool | Version | Install |
|------|---------|---------|
| Python | ≥ 3.9 | [python.org](https://python.org) |
| Docker Desktop | Latest | [docker.com](https://docker.com) |
| AWS CLI v2 | ≥ 2.x | `brew install awscli` |
| boto3 | ≥ 1.26 | `pip install boto3` |
| sagemaker SDK | ≥ 2.150 | `pip install sagemaker` |

### AWS account setup
- An **AWS account** with billing enabled
- A **SageMaker Execution IAM Role** (see [Section 10](#10-iam-permissions))
- An **S3 bucket** (same region as SageMaker)
- **Amazon ECR** access

### Verify AWS CLI is configured
```bash
aws configure          # enter Access Key, Secret Key, region, output format
aws sts get-caller-identity   # should print your Account ID
```

---

## 3. Project Structure

```
student_resource 2/
├── Dockerfile                          ← Container definition for SageMaker
├── .gitignore
├── README.md                           ← Competition README
├── Documentation_template.md          ← Methodology write-up
│
├── code/
│   └── business_entity_resolution/
│       ├── requirements.txt            ← Python dependencies
│       ├── README.md                   ← How to reproduce locally
│       └── src/
│           ├── resolver.py             ← Core entity resolution engine
│           └── run_pipeline.py         ← End-to-end pipeline entrypoint
│
├── deploy/
│   ├── sagemaker_job.py                ← Submit SageMaker Processing Job
│   └── build_and_push_ecr.py          ← Build Docker image → push to ECR
│
├── utils/
│   └── validate_submission.py          ← Official competition validator
│
├── dataset/                            ← (gitignored) Competition data
└── output/                             ← (gitignored) Generated TSVs
```

---

## 4. Quick Start (Local)

Run the full pipeline locally before deploying to AWS:

```bash
# 1. Clone the repo
git clone https://github.com/rithika20252024/ml.git
cd ml

# 2. Install dependencies
pip install -r code/business_entity_resolution/requirements.txt

# 3. Place dataset files in dataset/
#    Expected: dataset/source1.csv, dataset/source2.csv, dataset/source3.csv
#    (Download from competition portal)

# 4. Run pipeline
python code/business_entity_resolution/src/run_pipeline.py

# 5. Validate output
python utils/validate_submission.py output/matching_results.tsv output/candidate_pairs.tsv
```

Expected runtime on a local machine (8 cores, 16 GB RAM): ~57 minutes  
Expected output:
- `output/matching_results.tsv` — ~181 MB, ~1.73M rows
- `output/candidate_pairs.tsv` — ~635 MB, ~1.73M rows

---

## 5. S3 Data Setup

### Create an S3 bucket
```bash
BUCKET="your-entity-resolution-bucket"
REGION="us-east-1"

aws s3 mb s3://${BUCKET} --region ${REGION}
```

### Upload the competition dataset
```bash
aws s3 cp dataset/ s3://${BUCKET}/data/ --recursive
```

Verify upload:
```bash
aws s3 ls s3://${BUCKET}/data/
```

Expected listing:
```
source1.csv
source2.csv
source3.csv
```

### Output folder (auto-created by SageMaker)
```
s3://your-entity-resolution-bucket/output/
    matching_results.tsv
    candidate_pairs.tsv
```

---

## 6. ECR Image Build & Push

This packages your Python code into a Docker container that SageMaker can run.

### Step 1 — Authenticate Docker to ECR
```bash
REGION="us-east-1"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

aws ecr get-login-password --region ${REGION} \
  | docker login --username AWS --password-stdin \
    ${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com
```

### Step 2 — Build the image
```bash
# From project root (where Dockerfile lives)
docker build -t entity-resolution:latest .
```

### Step 3 — Create ECR repository
```bash
aws ecr create-repository \
  --repository-name entity-resolution \
  --region ${REGION}
```

### Step 4 — Tag and push
```bash
IMAGE_URI="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/entity-resolution:latest"

docker tag entity-resolution:latest ${IMAGE_URI}
docker push ${IMAGE_URI}

echo "Image URI: ${IMAGE_URI}"
```

### Or use the helper script
```bash
python deploy/build_and_push_ecr.py \
  --repo-name entity-resolution \
  --region    us-east-1
```

---

## 7. SageMaker Processing Job

### Option A — Use the helper script (recommended)
```bash
python deploy/sagemaker_job.py \
  --s3-input  s3://your-entity-resolution-bucket/data/ \
  --s3-output s3://your-entity-resolution-bucket/output/ \
  --role      arn:aws:iam::123456789012:role/SageMakerExecutionRole \
  --image     123456789012.dkr.ecr.us-east-1.amazonaws.com/entity-resolution:latest \
  --instance  ml.m5.4xlarge
```

### Option B — AWS Console (no-code)
1. Go to **AWS Console → SageMaker → Processing → Create processing job**
2. Fill in:

| Field | Value |
|-------|-------|
| Job name | `entity-resolution-job` |
| IAM role | `SageMakerExecutionRole` |
| Container image | *(your ECR URI)* |
| Instance type | `ml.m5.4xlarge` |
| Instance count | `1` |
| Max runtime | `7200` seconds |
| Input — S3 URI | `s3://your-bucket/data/` |
| Input — Local path | `/opt/ml/processing/input` |
| Output — Local path | `/opt/ml/processing/output` |
| Output — S3 URI | `s3://your-bucket/output/` |

3. Click **Create job** and monitor in the console.

### Option C — Pure boto3 (for automation)
```python
import boto3, time

sm = boto3.client("sagemaker", region_name="us-east-1")

response = sm.create_processing_job(
    ProcessingJobName=f"entity-resolution-{int(time.time())}",
    RoleArn="arn:aws:iam::123456789012:role/SageMakerExecutionRole",
    AppSpecification={
        "ImageUri": "123456789012.dkr.ecr.us-east-1.amazonaws.com/entity-resolution:latest",
        "ContainerEntrypoint": ["python3", "/opt/ml/code/src/run_pipeline.py"],
        "ContainerArguments": [
            "--input-dir",  "/opt/ml/processing/input",
            "--output-dir", "/opt/ml/processing/output",
        ],
    },
    ProcessingResources={
        "ClusterConfig": {
            "InstanceCount": 1,
            "InstanceType": "ml.m5.4xlarge",
            "VolumeSizeInGB": 50,
        }
    },
    ProcessingInputs=[{
        "InputName": "dataset",
        "S3Input": {
            "S3Uri": "s3://your-entity-resolution-bucket/data/",
            "LocalPath": "/opt/ml/processing/input",
            "S3DataType": "S3Prefix",
            "S3InputMode": "File",
        },
    }],
    ProcessingOutputConfig={
        "Outputs": [{
            "OutputName": "results",
            "S3Output": {
                "S3Uri": "s3://your-entity-resolution-bucket/output/",
                "LocalPath": "/opt/ml/processing/output",
                "S3UploadMode": "EndOfJob",
            },
        }]
    },
    StoppingCondition={"MaxRuntimeInSeconds": 7200},
)

print("Job ARN:", response["ProcessingJobArn"])
```

### Recommended instance types

| Instance | vCPU | RAM | Notes | Est. Runtime |
|----------|------|-----|-------|-------------|
| `ml.m5.xlarge` | 4 | 16 GB | Minimum viable | ~90 min |
| `ml.m5.4xlarge` | 16 | 64 GB | **Recommended** | ~30 min |
| `ml.m5.12xlarge` | 48 | 192 GB | Fastest, higher cost | ~12 min |
| `ml.r5.4xlarge` | 16 | 128 GB | Memory-optimized | ~25 min |

> **Note:** The pipeline is single-threaded per country partition (France → US → India sequentially). Larger instance = more RAM for index building = faster.

---

## 8. SageMaker Pipeline (Orchestrated)

For production use, wrap the job in a **SageMaker Pipeline** for versioning, lineage, and scheduling.

```python
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.steps import ProcessingStep
from sagemaker.processing import ScriptProcessor, ProcessingInput, ProcessingOutput
import sagemaker

role    = "arn:aws:iam::123456789012:role/SageMakerExecutionRole"
session = sagemaker.Session()

processor = ScriptProcessor(
    image_uri="123456789012.dkr.ecr.us-east-1.amazonaws.com/entity-resolution:latest",
    command=["python3"],
    instance_type="ml.m5.4xlarge",
    instance_count=1,
    role=role,
    sagemaker_session=session,
)

step = ProcessingStep(
    name="EntityResolution",
    processor=processor,
    code="code/business_entity_resolution/src/run_pipeline.py",
    inputs=[
        ProcessingInput(
            source="s3://your-bucket/data/",
            destination="/opt/ml/processing/input",
        )
    ],
    outputs=[
        ProcessingOutput(
            source="/opt/ml/processing/output",
            destination="s3://your-bucket/output/",
        )
    ],
)

pipeline = Pipeline(
    name="EntityResolutionPipeline",
    steps=[step],
    sagemaker_session=session,
)

pipeline.upsert(role_arn=role)
pipeline.start()
```

---

## 9. Cost Estimation

All prices are **us-east-1** on-demand as of 2024. Actual costs vary by region.

| Resource | Rate | Est. Usage | Est. Cost |
|----------|------|-----------|-----------|
| `ml.m5.4xlarge` Processing | \$0.922/hr | 0.5 hr | **\$0.46** |
| S3 storage (input ~2 GB) | \$0.023/GB/mo | 2 GB | **\$0.05/mo** |
| S3 storage (output ~1 GB) | \$0.023/GB/mo | 1 GB | **\$0.02/mo** |
| ECR image storage (~1 GB) | \$0.10/GB/mo | 1 GB | **\$0.10/mo** |
| Data transfer (S3↔SageMaker) | Free (same region) | — | **\$0.00** |
| CloudWatch Logs | \$0.50/GB | ~10 MB | **\$0.01** |

**Total per run: ~\$0.46**  
**Total monthly (daily runs): ~\$14 + \$0.17 storage**

> **Cost tip:** Use `ml.m5.4xlarge` Spot instances for ~70% savings on batch jobs (add `--use-spot-instances` flag in boto3).

---

## 10. IAM Permissions

### Create the SageMaker execution role

1. **AWS Console → IAM → Roles → Create role**
2. Select trusted entity: **AWS service → SageMaker**
3. Attach these managed policies:
   - `AmazonSageMakerFullAccess`
   - `AmazonS3FullAccess` *(or scope to your bucket)*
   - `AmazonEC2ContainerRegistryReadOnly`

4. Name the role: `SageMakerExecutionRole`

### Minimal inline policy (scoped to your bucket)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::your-entity-resolution-bucket",
        "arn:aws:s3:::your-entity-resolution-bucket/data/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::your-entity-resolution-bucket/output/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:/aws/sagemaker/*"
    }
  ]
}
```

---

## 11. Monitoring & Logs

### View job status via CLI
```bash
aws sagemaker describe-processing-job \
  --processing-job-name entity-resolution-job \
  --query "ProcessingJobStatus"
```

### Stream logs from CloudWatch
```bash
aws logs tail \
  /aws/sagemaker/ProcessingJobs \
  --follow \
  --log-stream-name-prefix entity-resolution-job
```

### Download output from S3
```bash
aws s3 cp s3://your-entity-resolution-bucket/output/ ./output/ --recursive
```

### Validate downloaded output
```bash
python utils/validate_submission.py \
  output/matching_results.tsv \
  output/candidate_pairs.tsv
```

---

## 12. Troubleshooting

### ❌ `ResourceLimitExceeded: ml.m5.4xlarge`
- Request a **Service Quota increase** in the AWS Console for SageMaker Processing instances.
- Or fall back to `ml.m5.2xlarge` (16 GB RAM, ~2× slower).

### ❌ `ImagePullErrors` / ECR auth failure
```bash
# Re-authenticate Docker to ECR
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    <account-id>.dkr.ecr.us-east-1.amazonaws.com
```

### ❌ `AccessDenied` on S3
- Verify the IAM role has `s3:GetObject` on the input bucket and `s3:PutObject` on the output bucket.
- Ensure the bucket is in the **same region** as the SageMaker job.

### ❌ Job exits with `OOMKilled` (out of memory)
- Upgrade to a larger instance: `ml.m5.12xlarge` (192 GB) or `ml.r5.4xlarge` (128 GB).
- The India partition builds an in-memory index over ~4.7M records (~15 GB peak RAM).

### ❌ `ModuleNotFoundError: No module named 'resolver'`
- Ensure `PYTHONPATH=/opt/ml/code` is set in the Dockerfile (already done).
- Rebuild and re-push the ECR image after any code change.

### ❌ Output files missing from S3
- Check CloudWatch Logs for the job — the pipeline may have crashed mid-run.
- Verify `S3UploadMode: EndOfJob` is set (outputs only sync on successful completion).

---

## Appendix — Full End-to-End Workflow

```bash
# ── 1. One-time setup ────────────────────────────────────────────────────────
export BUCKET="your-entity-resolution-bucket"
export REGION="us-east-1"
export ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export ROLE="arn:aws:iam::${ACCOUNT}:role/SageMakerExecutionRole"
export IMAGE="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/entity-resolution:latest"

# Create S3 bucket
aws s3 mb s3://${BUCKET} --region ${REGION}

# Build & push Docker image to ECR
python deploy/build_and_push_ecr.py --repo-name entity-resolution --region ${REGION}

# ── 2. Upload data ───────────────────────────────────────────────────────────
aws s3 cp dataset/ s3://${BUCKET}/data/ --recursive

# ── 3. Run SageMaker Processing Job ─────────────────────────────────────────
python deploy/sagemaker_job.py \
  --s3-input  s3://${BUCKET}/data/ \
  --s3-output s3://${BUCKET}/output/ \
  --role      ${ROLE} \
  --image     ${IMAGE} \
  --instance  ml.m5.4xlarge

# ── 4. Download & validate results ──────────────────────────────────────────
aws s3 cp s3://${BUCKET}/output/ ./output/ --recursive
python utils/validate_submission.py output/matching_results.tsv output/candidate_pairs.tsv
```

---

*Document version: 1.0 | Generated for Amazon Business Entity Resolution Hackathon submission*
