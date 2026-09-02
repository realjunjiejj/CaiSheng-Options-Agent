#!/usr/bin/env bash
set -euo pipefail

command -v gcloud >/dev/null 2>&1 || {
  echo "ERROR: gcloud is required."
  exit 1
}
command -v curl >/dev/null 2>&1 || {
  echo "ERROR: curl is required for the post-deployment health check."
  exit 1
}

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${REGION:-us-central1}"
IMAGE_URI="${IMAGE_URI:-}"
UI_SERVICE_NAME="${UI_SERVICE_NAME:-caisheng-ui}"
UI_SERVICE_ACCOUNT_NAME="${UI_SERVICE_ACCOUNT_NAME:-caisheng-ui}"

if [[ -z "${PROJECT_ID}" || -z "${IMAGE_URI}" ]]; then
  echo "ERROR: PROJECT_ID and immutable IMAGE_URI are required."
  exit 1
fi
if [[ "${IMAGE_URI}" == *":latest" ]]; then
  echo "ERROR: an immutable image tag or digest is required; latest is forbidden."
  exit 1
fi

UI_SERVICE_ACCOUNT="${UI_SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts describe "${UI_SERVICE_ACCOUNT}" \
  --project="${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud iam service-accounts create "${UI_SERVICE_ACCOUNT_NAME}" \
  --project="${PROJECT_ID}" \
  --display-name="CaiSheng credential-free judge UI"

gcloud run deploy "${UI_SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE_URI}" \
  --service-account="${UI_SERVICE_ACCOUNT}" \
  --args="streamlit" \
  --allow-unauthenticated \
  --ingress=all \
  --port=8080 \
  --cpu=2 \
  --memory=2Gi \
  --min-instances=0 \
  --max-instances=3 \
  --timeout=300 \
  --execution-environment=gen2 \
  --set-env-vars="CAISHENG_PUBLIC_JUDGE_MODE=true,VOLAGENT_DATA_MODE=replay_synthetic,VOLAGENT_ALLOW_ORDER_SUBMISSION=false,VOLAGENT_REQUIRE_HUMAN_APPROVAL=true,VOLAGENT_ALPACA_PAPER_TRADE=true"

UI_URL="$(gcloud run services describe "${UI_SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format='value(status.url)')"

curl --fail --silent --show-error \
  --retry 12 --retry-all-errors --retry-delay 5 \
  "${UI_URL}/_stcore/health" >/dev/null

echo "PUBLIC_UI_URL=${UI_URL}"
echo "PUBLIC_UI_HEALTH=PASS"
