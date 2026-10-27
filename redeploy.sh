#!/usr/bin/env bash
# Build the image in ACR and point the scheduled job at it.
# Usage: ./redeploy.sh [tag]   (defaults to "latest")
set -euo pipefail

# On Windows, az's colorama log streaming crashes on non-ASCII build output
# (cp1252). --no-logs skips the stream; the build is still awaited and a
# failure still exits non-zero. Read logs afterwards with:
#   az acr task logs --registry <acr> --run-id <id>
export PYTHONIOENCODING=utf-8

cd "$(dirname "$0")"
source ./config.sh
TAG="${1:-latest}"

az acr build --no-logs --registry "$ACR_NAME" --image "$IMAGE_NAME:$TAG" --file containerfile \
  --build-arg CACHE_BUST="$(date +%s)" .

# Each execution pulls the image fresh, but pointing the job at the new tag
# keeps the template current.
az containerapp job update \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "$ACR_NAME.azurecr.io/$IMAGE_NAME:$TAG"
