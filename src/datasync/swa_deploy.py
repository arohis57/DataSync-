"""Publish the dashboard to an Azure Static Web App so it has a real, sign-in-protected URL.

The page is staged as index.html next to config/staticwebapp.config.json (the access rules) and
pushed with the SWA CLI. The deployment token is passed in the environment, never on the command
line, and is scrubbed from any error text.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SWA_CONFIG = ROOT / "config" / "staticwebapp.config.json"
TIMEOUT = 600


class SwaDeployError(RuntimeError):
    pass


def deploy(html: Path, token: str, config: Path = DEFAULT_SWA_CONFIG, runner=subprocess.run) -> None:
    """Replace the site's content with this dashboard as index.html. Raises SwaDeployError on failure."""
    with tempfile.TemporaryDirectory() as tmp:
        site = Path(tmp) / "site"
        site.mkdir()
        shutil.copyfile(html, site / "index.html")
        shutil.copyfile(config, site / "staticwebapp.config.json")
        env = {**os.environ, "SWA_CLI_DEPLOYMENT_TOKEN": token}
        try:
            res = runner(["swa", "deploy", str(site), "--env", "production"], env=env, capture_output=True,
                         text=True, timeout=TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise SwaDeployError(f"swa could not run: {type(e).__name__}") from None
    if res.returncode != 0:
        tail = ((res.stderr or "") + (res.stdout or "")).replace(token, "***").strip()[-500:]
        raise SwaDeployError(f"swa deploy exited {res.returncode}: {tail}")
