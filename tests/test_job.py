import base64
import json
import urllib.error

import pytest

from datasync import job
from datasync.agent import AgentResult
from datasync.job import pack_state, run_job, unpack_state
from datasync.workbook_writer import write_workbook
from test_agent import GOOD
from test_excel_to_model import tiny_payload

ENV = {"DATASYNC_INPUT_URL": "https://flow/in?sig=SECRET", "DATASYNC_PUBLISH_URL": "https://flow/out?sig=SECRET", "DATASYNC_NO_AGENT": "1"}


class Resp:
    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.raw


class Flows:
    """Stands in for urlopen: serves the input flow and records what is posted to the publish flow."""

    def __init__(self, tmp_path, input_error=None, publish_error=None):
        book = tmp_path / "w.xlsx"
        write_workbook(tiny_payload(), book)
        self.inputs = {"workbook_b64": base64.b64encode(book.read_bytes()).decode(), "state_b64": ""}
        self.input_error, self.publish_error, self.posted = input_error, publish_error, []

    def __call__(self, req, timeout=None):
        if req.full_url.startswith("https://flow/in"):
            if self.input_error:
                raise self.input_error
            return Resp(json.dumps(self.inputs).encode())
        if self.publish_error:
            raise self.publish_error
        self.posted.append(json.loads(req.data))
        return Resp(b"")


@pytest.fixture
def flows(tmp_path):
    return Flows(tmp_path)


def test_happy_path_publishes_dashboard_state_and_email(flows):
    assert run_job(ENV, flows) == 0
    (body,) = flows.posted
    assert body["publish"] and body["status"] == "PASS" and body["asof"] == "2026-10-25"
    assert body["dashboard"]["filename"] == "Phoenix R6 Program Cockpit.html"
    assert b"Phoenix R6 Program Cockpit" in base64.b64decode(body["dashboard"]["content_b64"])
    assert body["subject"].startswith("[Phoenix R6 Program Cockpit] PASS") and "Gaps" in body["email_html"]
    assert json.loads(base64.b64decode(body["state_b64"]))["digests"].keys() == {"2026-10-25"}


def test_blocked_run_sends_the_email_but_no_dashboard_or_state(flows, monkeypatch):
    monkeypatch.setattr("datasync.run_refresh.analyze", lambda d, **kw: AgentResult({**GOOD, "status": "FAIL"}))
    assert run_job({**ENV, "DATASYNC_NO_AGENT": "0"}, flows) == 1
    (body,) = flows.posted
    assert not body["publish"] and body["dashboard"] is None and body["state_b64"] is None
    assert body["subject"].endswith("NOT published")


def test_failed_fetch_sends_a_failure_notice(tmp_path):
    flows = Flows(tmp_path, input_error=urllib.error.URLError("down"))
    assert run_job(ENV, flows) == 1
    (body,) = flows.posted
    assert body["status"] == "FAIL" and "could not fetch the workbook" in body["email_text"] and body["dashboard"] is None


def test_input_without_a_workbook_is_a_failed_fetch(tmp_path):
    flows = Flows(tmp_path)
    flows.inputs = {"workbook_b64": ""}
    assert run_job(ENV, flows) == 1 and "could not fetch" in flows.posted[0]["email_text"]


def test_crash_in_the_refresh_sends_a_failure_notice(flows, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(job, "run_refresh", boom)
    assert run_job(ENV, flows) == 1
    assert "kaboom" in flows.posted[0]["email_text"]


def test_delivery_failure_fails_the_job_without_retrying(tmp_path):
    flows = Flows(tmp_path, publish_error=urllib.error.URLError("down"))
    assert run_job(ENV, flows) == 1 and flows.posted == []


def test_missing_flow_urls_exit_2(flows):
    assert run_job({}, flows) == 2 and flows.posted == []


def test_urls_never_reach_the_logs(flows, caplog):
    caplog.set_level("DEBUG")
    run_job(ENV, flows)
    assert "SECRET" not in caplog.text


def test_state_bundle_round_trips(tmp_path):
    src = tmp_path / "a"
    (src / "digests").mkdir(parents=True)
    (src / "burnup_history.json").write_text(json.dumps({"2026-10-18": ["1"]}), encoding="utf-8")
    (src / "digests" / "2026-10-25.json").write_text(json.dumps({"asof": "2026-10-25"}), encoding="utf-8")
    dst = tmp_path / "b"
    unpack_state(pack_state(src), dst)
    assert json.loads((dst / "burnup_history.json").read_text()) == {"2026-10-18": ["1"]}
    assert json.loads((dst / "digests" / "2026-10-25.json").read_text()) == {"asof": "2026-10-25"}


def test_state_bundle_keeps_only_the_newest_digests(tmp_path):
    (tmp_path / "digests").mkdir()
    days = [f"2026-09-{d:02d}" for d in range(1, 31)] + [f"2026-10-{d:02d}" for d in range(1, 6)]
    for day in days:
        (tmp_path / "digests" / f"{day}.json").write_text("{}")
    kept = json.loads(base64.b64decode(pack_state(tmp_path)))["digests"]
    assert len(kept) == 30 and "2026-09-01" not in kept and "2026-10-05" in kept


@pytest.mark.parametrize("blob", [None, "", "!!!not base64!!!", base64.b64encode(b"{}").decode()])
def test_unreadable_or_empty_state_starts_fresh(tmp_path, blob):
    unpack_state(blob, tmp_path / "s")
    assert not (tmp_path / "s").exists()


SWA_ENV = {**ENV, "DATASYNC_SWA_TOKEN": "TOKEN123", "DATASYNC_DASHBOARD_URL": "https://site.azurestaticapps.net"}


def test_dashboard_is_deployed_and_linked_in_the_email(flows):
    calls = []
    assert run_job(SWA_ENV, flows, lambda html, token: calls.append((html.read_bytes()[:15], token))) == 0
    assert len(calls) == 1 and calls[0][1] == "TOKEN123"
    (body,) = flows.posted
    assert body["dashboard_url"] == "https://site.azurestaticapps.net"
    assert body["email_html"].startswith('<p><a href="https://site.azurestaticapps.net">')
    assert body["email_text"].startswith("Dashboard: https://site.azurestaticapps.net\n")


def test_failed_deploy_publishes_nothing_and_sends_a_failure_notice(flows):
    def boom(html, token):
        raise job.swa_deploy.SwaDeployError("swa deploy exited 1")

    assert run_job(SWA_ENV, flows, boom) == 1
    (body,) = flows.posted
    assert not body["publish"] and body["dashboard"] is None and "swa deploy exited 1" in body["email_text"]
    assert "TOKEN123" not in body["email_text"]


def test_blocked_run_does_not_deploy(flows, monkeypatch):
    monkeypatch.setattr("datasync.run_refresh.analyze", lambda d, **kw: AgentResult({**GOOD, "status": "FAIL"}))
    calls = []
    run_job({**SWA_ENV, "DATASYNC_NO_AGENT": "0"}, flows, lambda *a: calls.append(a))
    assert calls == []
