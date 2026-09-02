#!/usr/bin/env bash
set -euo pipefail

command -v gcloud >/dev/null 2>&1 || {
  echo "ERROR: gcloud is required."
  exit 1
}

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${REGION:-us-central1}"
REPOSITORY="${REPOSITORY:-caisheng}"
IMAGE_NAME="${IMAGE_NAME:-caisheng-trading}"
TAG="${TAG:-$(git rev-parse --short=12 HEAD 2>/dev/null || true)}"
UI_SERVICE_NAME="${UI_SERVICE_NAME:-caisheng-ui}"
MCP_SERVICE_NAME="${MCP_SERVICE_NAME:-caisheng-mcp}"
UI_SERVICE_ACCOUNT_NAME="${UI_SERVICE_ACCOUNT_NAME:-caisheng-ui}"
MCP_SERVICE_ACCOUNT_NAME="${MCP_SERVICE_ACCOUNT_NAME:-caisheng-mcp}"
ALPACA_API_KEY_SECRET="${ALPACA_API_KEY_SECRET:-caisheng_alpaca_api_key}"
ALPACA_SECRET_KEY_SECRET="${ALPACA_SECRET_KEY_SECRET:-caisheng_alpaca_secret_key}"
MCP_INVOKER_MEMBER="${MCP_INVOKER_MEMBER:-}"

if [[ -z "${PROJECT_ID}" || -z "${TAG}" ]]; then
  echo "ERROR: PROJECT_ID and immutable TAG are required."
  exit 1
fi
if [[ "${TAG}" == "latest" ]]; then
  echo "ERROR: TAG=latest is forbidden."
  exit 1
fi

IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${TAG}"
UI_SERVICE_ACCOUNT="${UI_SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
MCP_SERVICE_ACCOUNT="${MCP_SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

ensure_service_account() {
  local account_name="$1"
  local display_name="$2"
  gcloud iam service-accounts describe \
    "${account_name}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --project="${PROJECT_ID}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${account_name}" \
    --project="${PROJECT_ID}" \
    --display-name="${display_name}"
}

ensure_service_account "${UI_SERVICE_ACCOUNT_NAME}" "CaiSheng judge UI"
ensure_service_account "${MCP_SERVICE_ACCOUNT_NAME}" "CaiSheng private MCP"

for secret_name in "${ALPACA_API_KEY_SECRET}" "${ALPACA_SECRET_KEY_SECRET}"; do
  gcloud secrets describe "${secret_name}" --project="${PROJECT_ID}" >/dev/null
  gcloud secrets add-iam-policy-binding "${secret_name}" \
    --project="${PROJECT_ID}" \
    --member="serviceAccount:${MCP_SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" >/dev/null
done

echo "Deploying public read-only judge UI..."
gcloud run deploy "${UI_SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE_URI}" \
  --service-account="${UI_SERVICE_ACCOUNT}" \
  --args="streamlit" \
  --allow-unauthenticated \
  --port=8080 \
  --cpu=2 \
  --memory=2Gi \
  --min-instances=0 \
  --max-instances=3 \
  --timeout=300 \
  --execution-environment=gen2 \
  --set-env-vars="CAISHENG_PUBLIC_JUDGE_MODE=true,VOLAGENT_DATA_MODE=replay_synthetic,VOLAGENT_ALLOW_ORDER_SUBMISSION=false,VOLAGENT_REQUIRE_HUMAN_APPROVAL=true,VOLAGENT_ALPACA_PAPER_TRADE=true"

echo "Deploying private authenticated MCP service..."
gcloud run deploy "${MCP_SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE_URI}" \
  --service-account="${MCP_SERVICE_ACCOUNT}" \
  --args="streamable-http" \
  --no-allow-unauthenticated \
  --port=8080 \
  --cpu=1 \
  --memory=1Gi \
  --min-instances=0 \
  --max-instances=1 \
  --timeout=3600 \
  --execution-environment=gen2 \
  --set-env-vars="VOLAGENT_DATA_MODE=live,VOLAGENT_ALLOW_ORDER_SUBMISSION=false,VOLAGENT_REQUIRE_HUMAN_APPROVAL=true,VOLAGENT_ALPACA_PAPER_TRADE=true" \
  --set-secrets="ALPACA_API_KEY=${ALPACA_API_KEY_SECRET}:latest,ALPACA_SECRET_KEY=${ALPACA_SECRET_KEY_SECRET}:latest"

UI_URL="$(gcloud run services describe "${UI_SERVICE_NAME}" --project="${PROJECT_ID}" --region="${REGION}" --format='value(status.url)')"
MCP_URL="$(gcloud run services describe "${MCP_SERVICE_NAME}" --project="${PROJECT_ID}" --region="${REGION}" --format='value(status.url)')"

if [[ -n "${MCP_INVOKER_MEMBER}" ]]; then
  gcloud run services add-iam-policy-binding "${MCP_SERVICE_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --member="${MCP_INVOKER_MEMBER}" \
    --role="roles/run.invoker" >/dev/null
fi

echo "UI_URL=${UI_URL}"
echo "MCP_URL=${MCP_URL}/mcp"
if [[ -z "${MCP_INVOKER_MEMBER}" ]]; then
  echo "MCP has no caller binding. Set MCP_INVOKER_MEMBER=user:you@example.com and redeploy."
else
  echo "MCP invoker granted to ${MCP_INVOKER_MEMBER}."
fi
echo "MCP authentication is required; invoke with a Google-signed identity token."
