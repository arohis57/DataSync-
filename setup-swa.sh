#!/usr/bin/env bash
# Creates the Static Web App that hosts the dashboard and wires it into the job:
#   - DATASYNC_SWA_TOKEN (secret)    deployment token the job uses to publish
#   - DATASYNC_DASHBOARD_URL (plain) the site address, linked in the report email
# Run after ./deploy.sh. Idempotent. Then invite each viewer (see the end of the output).
set -euo pipefail
export PYTHONIOENCODING=utf-8

cd "$(dirname "$0")"
source ./config.sh

az account show >/dev/null || { echo "Run 'az login' first."; exit 1; }

echo "==> Static Web App ($SWA_SKU)"
az staticwebapp show --name "$SWA_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1 \
  || az staticwebapp create --name "$SWA_NAME" --resource-group "$RESOURCE_GROUP" \
       --location "$SWA_LOCATION" --sku "$SWA_SKU" >/dev/null

HOST=$(az staticwebapp show --name "$SWA_NAME" --resource-group "$RESOURCE_GROUP" --query defaultHostname -o tsv)
TOKEN=$(az staticwebapp secrets list --name "$SWA_NAME" --resource-group "$RESOURCE_GROUP" --query properties.apiKey -o tsv)

echo "==> Wiring the job"
az containerapp job secret set --name "$JOB_NAME" --resource-group "$RESOURCE_GROUP" \
  --secrets datasync-swa-token="$TOKEN" >/dev/null
az containerapp job update --name "$JOB_NAME" --resource-group "$RESOURCE_GROUP" \
  --set-env-vars DATASYNC_SWA_TOKEN=secretref:datasync-swa-token "DATASYNC_DASHBOARD_URL=https://$HOST" >/dev/null

echo "==> Done. Dashboard address: https://$HOST"
echo "    Nobody can open it until invited with the 'reader' role (Azure portal > $SWA_NAME > Role management > Invite),"
echo "    or: az staticwebapp users invite -n $SWA_NAME -g $RESOURCE_GROUP --authentication-provider aad \\"
echo "          --user-details <email> --roles reader --domain $HOST --invitation-expiration-in-hours 168"
echo "    Rebuild the image first (./redeploy.sh): the job needs the SWA CLI that this version adds."
