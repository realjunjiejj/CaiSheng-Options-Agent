#!/usr/bin/env bash
set -euo pipefail

command -v gcloud >/dev/null 2>&1 || {
  echo "ERROR: gcloud is required for Artifact Registry and Cloud Build."
  exit 1
}

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${REGION:-us-central1}"
REPOSITORY="${REPOSITORY:-caisheng}"
IMAGE_NAME="${IMAGE_NAME:-caisheng-trading}"
TAG="${TAG:-$(git rev-parse --short=12 HEAD 2>/dev/null || true)}"

if [[ -z "${PROJECT_ID}" || -z "${TAG}" ]]; then
  echo "ERROR: PROJECT_ID and an immutable TAG are required."
  exit 1
fi
if [[ "${TAG}" == "latest" ]]; then
  echo "ERROR: TAG=latest is forbidden; use a Git commit SHA or release identifier."
  exit 1
fi
if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: refusing to build a Git-SHA image from a dirty worktree."
  echo "Commit the reviewed source first so the deployed image is reproducible."
  exit 1
fi

IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${TAG}"

gcloud artifacts repositories describe "${REPOSITORY}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" >/dev/null 2>&1 || \
gcloud artifacts repositories create "${REPOSITORY}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --repository-format=docker \
  --description="CaiSheng Options Alpha images"

echo "Building immutable image ${IMAGE_URI}"
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE_URI}" \
  .

echo "IMAGE_URI=${IMAGE_URI}"
