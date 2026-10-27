# Shared settings sourced by deploy.sh, redeploy.sh and set-secrets.sh.
# Each value can be overridden from the environment.
RESOURCE_GROUP="${RESOURCE_GROUP:-datasync-rg}"
LOCATION="${LOCATION:-eastus}"
# ACR names are globally unique across Azure - change this if creation fails.
ACR_NAME="${ACR_NAME:-datasyncacr52917}"
ENV_NAME="${ENV_NAME:-datasync-env}"
JOB_NAME="${JOB_NAME:-datasync-job}"
IMAGE_NAME="${IMAGE_NAME:-datasync}"
# Cron is evaluated in UTC. 13:00 UTC = 8:00 AM CDT (UTC-5), Mon-Fri; when Central
# returns to CST (UTC-6, November) use "0 14 * * 1-5" to keep 8:00 AM Central.
# Set it to run AFTER the ADO-to-Excel export has refreshed the workbook in SharePoint.
CRON_EXPRESSION="${CRON_EXPRESSION:-0 13 * * 1-5}"
# Who gets the refresh report. ";"-separated addresses; blank = the publish flow decides.
EMAIL_TO="${EMAIL_TO:-}"
EMAIL_CC="${EMAIL_CC:-}"
