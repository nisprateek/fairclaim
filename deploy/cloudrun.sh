#!/usr/bin/env bash
# Deploy fairclaim to Cloud Run.
#
# Prerequisites:
#   1. gcloud auth login
#   2. A GCP project with billing enabled.
#
# Usage:
#   PROJECT_ID=your-project ./deploy/cloudrun.sh
#
# This deploys the existing Cloud Run service name `fairclaimai` in
# europe-west2 by default, preserving the live URL:
#   https://fairclaimai-698454199279.europe-west2.run.app/
#
# GEMINI_API_KEY is read from .env and stored in Secret Manager. It is never
# baked into the image or printed by this script.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID, e.g. PROJECT_ID=my-gcp-project ./deploy/cloudrun.sh}"
REGION="${REGION:-europe-west2}"
SERVICE_NAME="${SERVICE_NAME:-fairclaimai}"
SECRET_NAME="${SECRET_NAME:-gemini-api-key}"

if [ ! -f .env ] || ! grep -q '^GEMINI_API_KEY=' .env; then
  echo ".env must contain GEMINI_API_KEY=... (see .envexample)." >&2
  exit 1
fi
GEMINI_API_KEY="$(grep '^GEMINI_API_KEY=' .env | cut -d= -f2-)"

echo "==> Project: ${PROJECT_ID}  Region: ${REGION}  Service: ${SERVICE_NAME}"
gcloud config set project "${PROJECT_ID}" >/dev/null

echo "==> Enabling required APIs"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com >/dev/null

if gcloud secrets describe "${SECRET_NAME}" >/dev/null 2>&1; then
  echo "==> Adding a new version to existing secret ${SECRET_NAME}"
  printf '%s' "${GEMINI_API_KEY}" | gcloud secrets versions add "${SECRET_NAME}" --data-file=-
else
  echo "==> Creating secret ${SECRET_NAME}"
  printf '%s' "${GEMINI_API_KEY}" | gcloud secrets create "${SECRET_NAME}" --data-file=-
fi

COMPUTE_SA="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
echo "==> Ensuring ${COMPUTE_SA} can build and read the secret"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${COMPUTE_SA}" --role="roles/cloudbuild.builds.builder" >/dev/null
gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --member="serviceAccount:${COMPUTE_SA}" --role="roles/secretmanager.secretAccessor" >/dev/null

echo "==> Building and deploying with Cloud Build"
gcloud run deploy "${SERVICE_NAME}" \
  --source=. \
  --region="${REGION}" \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=1 \
  --memory=1Gi \
  --set-secrets="GEMINI_API_KEY=${SECRET_NAME}:latest"

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --format='value(status.url)')"
echo "==> Live at: ${SERVICE_URL}"
echo "==> Expected stable service URL: https://fairclaimai-698454199279.europe-west2.run.app/"
