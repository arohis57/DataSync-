#!/usr/bin/env bash
# One-time bootstrap: provisions the resource group, ACR and Container Apps
# environment, then builds the image and creates the scheduled DataSync job.
# Idempotent - safe to re-run. Use ./redeploy.sh for later image updates.
#
# Secrets: if CLAUDE_CODE_OAUTH_TOKEN, DATASYNC_INPUT_URL and DATASYNC_PUBLISH_URL are set
# in your shell (or in a local .env), they are wired in automatically via ./set-secrets.sh.
# Otherwise run that script later. CLAUDE_CODE_OAUTH_TOKEN comes from `claude setup-token`.
set -euo pipefail
export PYTHONIOENCODING=utf-8

cd "$(dirname "$0")"
source ./config.sh
IMAGE_TAG="${1:-v1}"

az account show >/dev/null || { echo "Run 'az login' first."; exit 1; }

echo "==> Resource group"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" >/dev/null

echo "==> Registering resource providers"
az provider register --namespace Microsoft.ContainerRegistry --wait
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait

echo "==> Container extension"
az extension add --name containerapp --upgrade -y

echo "==> Container registry"
az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --sku Basic --admin-enabled true >/dev/null

echo "==> Container Apps environment"
az containerapp env create --name "$ENV_NAME" --resource-group "$RESOURCE_GROUP" --location "$LOCATION" >/dev/null

echo "==> Building and pushing image (build logs: az acr task logs --registry $ACR_NAME)"
az acr build --no-logs --registry "$ACR_NAME" --image "$IMAGE_NAME:$IMAGE_TAG" --file containerfile \
  --build-arg CACHE_BUST="$(date +%s)" .

ACR_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)
ACR_USER=$(az acr credential show --name "$ACR_NAME" --query username -o tsv)
ACR_PASS=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)

# Plain (non-secret) settings; recipients are only added when set.
ENV_VARS=("DATASYNC_AGENT_BACKEND=cli")
[[ -n "$EMAIL_TO" ]] && ENV_VARS+=("DATASYNC_EMAIL_TO=$EMAIL_TO")
[[ -n "$EMAIL_CC" ]] && ENV_VARS+=("DATASYNC_EMAIL_CC=$EMAIL_CC")

echo "==> Creating scheduled job ($CRON_EXPRESSION UTC)"
# Each execution is a fresh container that runs datasync.job and exits.
# replica-retry-limit 0: a failed run is not retried, to avoid sending the report twice.
az containerapp job create \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENV_NAME" \
  --trigger-type Schedule \
  --cron-expression "$CRON_EXPRESSION" \
  --replica-timeout 1800 \
  --replica-retry-limit 0 \
  --parallelism 1 \
  --replica-completion-count 1 \
  --image "$ACR_SERVER/$IMAGE_NAME:$IMAGE_TAG" \
  --registry-server "$ACR_SERVER" \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --cpu 1.0 --memory 2.0Gi \
  --env-vars "${ENV_VARS[@]}" >/dev/null

if [[ -f .env ]]; then set -a; source .env; set +a; fi
if [[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" && -n "${DATASYNC_INPUT_URL:-}" && -n "${DATASYNC_PUBLISH_URL:-}" ]]; then
  echo "==> Setting secrets from environment"
  ./set-secrets.sh
else
  echo "==> Skipping secrets (not all three variables are set)"
  echo "    Runs will fail until you run ./set-secrets.sh."
fi

echo "==> Done. Job: $JOB_NAME (schedule: $CRON_EXPRESSION UTC)"
echo "    Run now:   az containerapp job start -n $JOB_NAME -g $RESOURCE_GROUP"
echo "    History:   az containerapp job execution list -n $JOB_NAME -g $RESOURCE_GROUP -o table"
