#!/usr/bin/env bash
# Sets the job's runtime secrets on the Container Apps Job.
# Values come from the shell environment or a local, git-ignored .env file:
#   CLAUDE_CODE_OAUTH_TOKEN  from `claude setup-token` (one-year token)
#   DATASYNC_INPUT_URL       URL of the "Get inputs" Power Automate flow
#   DATASYNC_PUBLISH_URL     URL of the "Publish" Power Automate flow
# Usage: ./set-secrets.sh
set -euo pipefail

cd "$(dirname "$0")"
source ./config.sh
if [[ -f .env ]]; then set -a; source .env; set +a; fi

for v in CLAUDE_CODE_OAUTH_TOKEN DATASYNC_INPUT_URL DATASYNC_PUBLISH_URL; do
  [[ -n "${!v:-}" ]] || { echo "Missing $v (set it in your environment or .env)"; exit 1; }
done

az containerapp job secret set \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --secrets \
    claude-code-oauth-token="$CLAUDE_CODE_OAUTH_TOKEN" \
    datasync-input-url="$DATASYNC_INPUT_URL" \
    datasync-publish-url="$DATASYNC_PUBLISH_URL" >/dev/null

az containerapp job update \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --set-env-vars \
    CLAUDE_CODE_OAUTH_TOKEN=secretref:claude-code-oauth-token \
    DATASYNC_INPUT_URL=secretref:datasync-input-url \
    DATASYNC_PUBLISH_URL=secretref:datasync-publish-url >/dev/null

echo "Secrets set and job updated."
