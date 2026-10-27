# DataSync

Keeps the Phoenix Program Cockpit dashboard in sync with Azure DevOps.

```
ADO ─► Excel workbook (SharePoint) ─► excel_to_model ─► agent ─► generate_cockpit ─► HTML ─► SharePoint
```

| Step | Code | Status |
|---|---|---|
| ADO to Excel | not written yet | todo |
| Excel to payload | `src/datasync/excel_to_model.py` | done |
| Validate / insights agent | `src/datasync/digest.py`, `agent.py`, prompt in `src/DataSync_prompt.md` | built, not yet run against the live API |
| Render HTML (fixed template) | `src/cockpit/generate_cockpit.py` | done |
| Orchestrator (one full refresh, decision, email report) | `src/datasync/run_refresh.py`, `report_email.py` | done |
| Azure job (fetch, refresh, publish) | `src/datasync/job.py`, `containerfile`, `deploy.sh` and friends | written, not deployed |
| Move files in and out of SharePoint, send the email | Power Automate, see [docs/power_automate.md](docs/power_automate.md) | flows not built yet |

The workbook layout and payload format are in [docs/data_model.md](docs/data_model.md).

## Setup

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

## Use

```
# build a sample workbook from the reference payload
.venv\Scripts\python scripts\make_sample_workbook.py

# workbook -> payload (+ build\validation_report.json)
.venv\Scripts\python -m datasync.excel_to_model samples\Phoenix_R6_DataSync.xlsx -o build\cockpit_data.json

# one full refresh (what the daily job runs). Writes everything to build\, remembers state in state\
#   build\cockpit.html + cockpit_data.json   only when the decision is to publish
#   build\email.html / email.txt / email.json  the gaps report, every run
# --no-agent skips the AI step (no API key needed). Exit code 0 = published, 1 = not published.
.venv\Scripts\python -m datasync.run_refresh samples\Phoenix_R6_DataSync.xlsx --no-agent
# recipients for email.json: set DATASYNC_EMAIL_TO / DATASYNC_EMAIL_CC (";"-separated)

# the individual steps, for debugging
# agent step: --dry-run builds build\digest.json and the request without calling the API;
# without it, calls Claude (needs ANTHROPIC_API_KEY) and writes build\agent_result.json
.venv\Scripts\python -m datasync.agent --dry-run
.venv\Scripts\python -m datasync.agent

# payload -> dashboard
.venv\Scripts\python src\cockpit\generate_cockpit.py build\cockpit_data.json build\cockpit.html

.venv\Scripts\python -m pytest
```

Static dashboard text (titles, footnotes, org lists) lives in `config/cockpit_config.json`.

## Agent backends

The AI step runs through headless Claude Code (`claude -p`, auth `CLAUDE_CODE_OAUTH_TOKEN`), the same way TaskLens does, or through the Anthropic API (`ANTHROPIC_API_KEY`). `DATASYNC_AGENT_BACKEND=cli|api` picks one; otherwise `cli` is used when the token is set. The job image sets `cli`.

## Deploy to Azure (Container Apps Job)

Same pattern as TaskLens: the image is built remotely in ACR (no local Docker), and the job runs on a cron schedule with 0 retries so a failed run can't send the report twice.

| File | Purpose |
|---|---|
| `config.sh` | Resource names, `CRON_EXPRESSION` (UTC), `EMAIL_TO` / `EMAIL_CC` |
| `deploy.sh` | One-time bootstrap: resource group, ACR, Container Apps environment, image, scheduled job |
| `redeploy.sh` | Rebuild the image and point the job at it |
| `set-secrets.sh` | Store `CLAUDE_CODE_OAUTH_TOKEN`, `DATASYNC_INPUT_URL`, `DATASYNC_PUBLISH_URL` on the job |

Build the two Power Automate flows first ([docs/power_automate.md](docs/power_automate.md)), then:

```
az login
cp .env.example .env     # fill in the three values
./deploy.sh
az containerapp job start -n datasync-job -g datasync-rg      # run now
az containerapp job execution list -n datasync-job -g datasync-rg -o table
```

Test the job locally against `scripts/mock_flows.py` first. The job exits 0 only when the dashboard was published and delivered, so blocked or failed runs show as failed executions.
