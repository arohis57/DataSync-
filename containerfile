# syntax=docker/dockerfile:1
#
# DataSync - daily job that turns the ADO workbook (SharePoint) into the Phoenix Program Cockpit.
#
# Bundled:
#   1. Python 3.12 + the datasync package (workbook -> payload -> dashboard HTML)
#   2. Node + the SWA CLI, to publish the dashboard to Azure Static Web Apps
#   3. Claude Code CLI, used headless (`claude -p`) for the validation / insights step, same as TaskLens
#
# Runtime secrets (never baked in; injected as Container Apps secrets):
#   CLAUDE_CODE_OAUTH_TOKEN  headless Claude auth (`claude setup-token`)
#   DATASYNC_INPUT_URL       Power Automate flow that returns the workbook and saved state
#   DATASYNC_PUBLISH_URL     Power Automate flow that uploads the dashboard and sends the email
#   DATASYNC_SWA_TOKEN       deployment token of the Static Web App that hosts the dashboard (optional)
# Plain env var DATASYNC_DASHBOARD_URL is the site's address, linked in the email.
# Plain env vars: DATASYNC_EMAIL_TO / DATASYNC_EMAIL_CC (";"-separated), DATASYNC_AGENT_BACKEND.

FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @azure/static-web-apps-cli \
    && swa --version

# Non-root user with a real $HOME: Claude Code writes ~/.claude.
RUN useradd --create-home --home-dir /home/appuser --shell /bin/bash appuser \
    && mkdir -p /app \
    && chown appuser:appuser /app
USER appuser
WORKDIR /app

ENV HOME=/home/appuser \
    PATH="/home/appuser/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    DATASYNC_AGENT_BACKEND=cli

RUN curl -fsSL https://claude.ai/install.sh | bash \
    && claude --version

# CACHE_BUST defeats stale ACR Tasks layer caching for the source COPY; the RUN
# must reference the arg for Docker to honour it. Pass a fresh value per build.
ARG CACHE_BUST=0
RUN echo "cache_bust=${CACHE_BUST}" > /dev/null
COPY --chown=appuser:appuser . .

# Editable, so the package finds /app/config and /app/src/cockpit/generate_cockpit.py next to the source.
RUN pip install --no-cache-dir --user -e .

# Scheduled run: fetch -> refresh -> publish, then exit (see src/datasync/job.py).
CMD ["python", "-m", "datasync.job"]
