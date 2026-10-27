"""Scheduled entrypoint for the Azure Container Apps Job.

Mirrors TaskLens: no storage account, Power Automate does all the SharePoint work over HTTP.

  1. POST DATASYNC_INPUT_URL   -> flow returns {workbook_b64, state_b64}   (SharePoint -> job)
  2. run_refresh on a temp folder
  3. POST DATASYNC_PUBLISH_URL <- {status, publish, email_*, dashboard, state_b64}   (job -> SharePoint + email)

The flow URLs carry a signature, so they are secrets and are never logged. DATASYNC_NO_AGENT=1 skips
the AI step. Exit code 0 means the dashboard was published and delivered; anything else shows up as
a failed execution in Azure.
See docs/power_automate.md for the two flows.
"""
from __future__ import annotations

import base64
import html
import json
import logging
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

from .run_refresh import _dump, _load, run_refresh
from .report_email import _recipients

log = logging.getLogger("datasync")
KEEP_DIGESTS = 30  # days of past digests carried in the state bundle


def pack_state(state_dir: Path) -> str:
    """The state folder as one base64 JSON blob (burn-up snapshots + the newest digests)."""
    digests = sorted((state_dir / "digests").glob("*.json"))[-KEEP_DIGESTS:]
    bundle = {"version": 1, "burnup_history": _load(state_dir / "burnup_history.json", {}),
              "digests": {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in digests}}
    return base64.b64encode(json.dumps(bundle, ensure_ascii=False).encode("utf-8")).decode("ascii")


def unpack_state(blob_b64: str | None, state_dir: Path) -> None:
    """Restore a state bundle into state_dir. A blank or unreadable blob means a first run: start empty."""
    if not blob_b64:
        return
    try:
        bundle = json.loads(base64.b64decode(blob_b64).decode("utf-8"))
        history, digests = bundle["burnup_history"], bundle["digests"]
    except (ValueError, KeyError, TypeError) as e:
        log.warning("state bundle unreadable (%s); starting with empty state", e)
        return
    _dump(state_dir / "burnup_history.json", history)
    for day, digest in digests.items():
        _dump(state_dir / "digests" / f"{day}.json", digest)


def post_json(url: str, body: dict, timeout: int, opener=urllib.request.urlopen) -> dict | None:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    with opener(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def fetch_inputs(url: str, opener=urllib.request.urlopen) -> dict:
    inputs = post_json(url, {"request": "inputs"}, 120, opener)
    if not isinstance(inputs, dict) or not inputs.get("workbook_b64"):
        raise ValueError("the input flow returned no workbook_b64")
    return inputs


def publish_body(summary: dict, out_dir: Path, state_dir: Path) -> dict:
    email = json.loads((out_dir / "email.json").read_text(encoding="utf-8"))
    body = {**email, "asof": summary["asof"], "reason": summary["reason"],
            "email_html": (out_dir / "email.html").read_text(encoding="utf-8"),
            "email_text": (out_dir / "email.txt").read_text(encoding="utf-8"),
            "dashboard": None, "state_b64": None}
    if summary["publish"]:
        title = json.loads((out_dir / "cockpit_data.json").read_text(encoding="utf-8"))["title"]
        body["dashboard"] = {"filename": f"{html.unescape(title)}.html",
                             "content_b64": base64.b64encode((out_dir / "cockpit.html").read_bytes()).decode("ascii")}
        body["state_b64"] = pack_state(state_dir)
    return body


def notify_failure(url: str, what: str, opener=urllib.request.urlopen) -> None:
    """Tell people the refresh itself broke (nothing was published, state is untouched)."""
    text = f"The DataSync refresh could not complete: {what}. Nothing was published."
    body = {"status": "FAIL", "publish": False, "asof": None, "reason": what, "subject": "[DataSync] Refresh failed - NOT published",
            "email_html": f"<p>{html.escape(text)}</p>", "email_text": text, "to": _recipients("DATASYNC_EMAIL_TO"),
            "cc": _recipients("DATASYNC_EMAIL_CC"), "dashboard": None, "state_b64": None}
    try:
        post_json(url, body, 60, opener)
    except Exception as e:  # noqa: BLE001 - already failing; the non-zero exit code still flags the execution
        log.error("could not send the failure notice: %s", type(e).__name__)


def run_job(env=os.environ, opener=urllib.request.urlopen) -> int:
    input_url, publish_url = env.get("DATASYNC_INPUT_URL"), env.get("DATASYNC_PUBLISH_URL")
    if not input_url or not publish_url:
        log.error("DATASYNC_INPUT_URL and DATASYNC_PUBLISH_URL must both be set")
        return 2
    try:
        inputs = fetch_inputs(input_url, opener)
    except Exception as e:  # noqa: BLE001
        log.error("could not fetch the workbook: %s: %s", type(e).__name__, e)
        notify_failure(publish_url, f"could not fetch the workbook from SharePoint ({type(e).__name__})", opener)
        return 1

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            workbook = tmp / "workbook.xlsx"
            workbook.write_bytes(base64.b64decode(inputs["workbook_b64"]))
            unpack_state(inputs.get("state_b64"), tmp / "state")
            summary = run_refresh(workbook, tmp / "out", tmp / "state", use_agent=env.get("DATASYNC_NO_AGENT") != "1")
            body = publish_body(summary, tmp / "out", tmp / "state")
    except Exception as e:  # noqa: BLE001
        log.exception("refresh crashed")
        notify_failure(publish_url, f"the refresh crashed ({type(e).__name__}: {e})", opener)
        return 1

    try:
        post_json(publish_url, body, 300, opener)
    except Exception as e:  # noqa: BLE001 - no retry: it could send the email twice
        log.error("delivery to Power Automate FAILED: %s: %s", type(e).__name__, e)
        return 1
    log.info("delivered: status=%s publish=%s", summary["status"], summary["publish"])
    return 0 if summary["publish"] else 1


def main() -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    return run_job()


if __name__ == "__main__":
    sys.exit(main())
