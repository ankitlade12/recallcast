#!/usr/bin/env bash

set -euo pipefail

required_variables=(
  B2_KEY_ID
  B2_APP_KEY
  B2_BUCKET
  B2_REGION
)

for variable_name in "${required_variables[@]}"; do
  if [[ -z "${!variable_name:-}" ]]; then
    echo "Missing required environment variable: ${variable_name}" >&2
    exit 1
  fi
done

if ! command -v aws >/dev/null 2>&1; then
  echo "AWS CLI is required for this verification script." >&2
  exit 1
fi

b2_endpoint="${B2_ENDPOINT:-https://s3.${B2_REGION}.backblazeb2.com}"

export AWS_ACCESS_KEY_ID="${B2_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${B2_APP_KEY}"
export AWS_DEFAULT_REGION="${B2_REGION}"

echo "Checking private bucket access at ${b2_endpoint}"
aws s3api head-bucket \
  --bucket "${B2_BUCKET}" \
  --endpoint-url "${b2_endpoint}"

echo "Checking bucket location"
aws s3api get-bucket-location \
  --bucket "${B2_BUCKET}" \
  --endpoint-url "${b2_endpoint}"

echo "Checking default encryption"
aws s3api get-bucket-encryption \
  --bucket "${B2_BUCKET}" \
  --endpoint-url "${b2_endpoint}"

echo "Checking CORS"
if ! aws s3api get-bucket-cors \
  --bucket "${B2_BUCKET}" \
  --endpoint-url "${b2_endpoint}"; then
  echo "CORS is not configured or is not readable by this key."
fi

echo "Checking lifecycle policy"
if ! aws s3api get-bucket-lifecycle-configuration \
  --bucket "${B2_BUCKET}" \
  --endpoint-url "${b2_endpoint}"; then
  echo "Lifecycle policy is not configured or is not readable by this key."
fi

echo "B2 verification complete."
