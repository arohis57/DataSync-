import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import pytest

from datasync.agent import (
    FALLBACK_BETA,
    PROMPT_PATH,
    SCHEMA,
    AgentResult,
    build_request,
    check_assessment,
    gate,
    load_prompt,
    run_agent,
)
from datasync.digest import build_digest
from datasync.excel_to_model import Report
from test_excel_to_model import tiny_payload

ROOT = Path(__file__).resolve().parents[1]
REAL_JSON = ROOT / "src" / "cockpit" / "cockpit_data.json"

GOOD = {
    "status": "WARNING",
    "validationSummary": {"missingValues": ["76 workshops have no target date"], "duplicateRecords": [], "dataQualityIssues": []},
    "metricsSummary": {"requirements": "r", "risks": "k", "actions": "a", "overallHealth": "h"},
    "executiveSummary": ["one", "two", "three"],
    "publishRecommendation": "Publish with review.",
}


def reply(text=None, stop_reason="end_turn", **kw):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text if text is not None else json.dumps(GOOD))],
                           model="claude-opus-5-5", usage=None, _request_id="req_1", **kw)


class FakeClient:
    def __init__(self, response=None, exc=None):
        self.calls = []
        self._response, self._exc = response or reply(), exc
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self._exc:
            raise self._exc
        return self._response


@pytest.fixture
def digest():
    return build_digest(tiny_payload(), Report().to_dict())


# --- digest -------------------------------------------------------------------

def test_digest_counts_tiny_payload(digest):
    k = digest["kpis"]
    assert k["workshops.in_scope"] == 1 and k["workshops.planned_to_date"] == 1
    assert k["requirements.traceability_pct"] == 100.0  # the one GAP requirement links to a build item
    assert k["pbis.without_parent"] == 1
    assert k["raid.open"] == 1 and k["raid.past_due"] == 1  # target 2026-10-01 < asof 2026-10-25
    assert digest["kpi_changes"] is None  # no previous refresh


def test_digest_reports_changes_against_previous(digest):
    previous = json.loads(json.dumps(digest))
    previous["kpis"]["raid.open"] = 0
    previous["asof"] = "2026-10-18"
    changed = build_digest(tiny_payload(), Report().to_dict(), previous)
    assert changed["previous_asof"] == "2026-10-18"
    assert changed["kpi_changes"]["raid.open"] == {"previous": 0, "now": 1, "change": 1}
    assert "workshops.in_scope" not in changed["kpi_changes"]  # unchanged values are left out


def test_digest_has_no_person_names(digest):
    assert "Doe" not in json.dumps(digest)


def test_digest_groups_workbook_warnings():
    rep = Report()
    for row in (5, 6, 7):
        rep.warn("Workshops", row, "Epic IDs", f"E id {row}99 not found; link dropped")
    out = build_digest(tiny_payload(), rep.to_dict())
    group = out["data_quality"]["warning_groups"][0]
    assert group["count"] == 3 and len(group["examples"]) == 3


def test_digest_flags_duplicate_titles_and_missing_dates():
    payload = tiny_payload()
    payload["data"]["W"].append(["201", "O2C", "Initiate - x", "New", "", None, []])
    out = build_digest(payload, Report().to_dict())
    assert out["data_quality"]["duplicate_records"][0]["sample_groups"] == [["200", "201"]]
    assert any(m["entity"] == "workshops" and m["field"] == "target date" for m in out["data_quality"]["missing_values"])


@pytest.mark.skipif(not REAL_JSON.exists(), reason="reference cockpit_data.json not present")
def test_digest_of_real_data_is_small():
    payload = json.loads(REAL_JSON.read_text(encoding="utf-8"))
    out = build_digest(payload, Report().to_dict())
    assert len(json.dumps(out)) < 40_000
    assert out["kpis"]["raid.open"] == 666


# --- request ------------------------------------------------------------------

def test_prompt_file_is_the_system_prompt(digest):
    prompt = load_prompt()
    assert prompt.startswith("You are DataSync") and PROMPT_PATH.stat().st_size > 0
    req = build_request(digest, prompt)
    assert req["system"] == prompt


def test_request_shape(digest):
    req = build_request(digest, "p")
    assert req["model"] == "claude-opus-5-5"
    assert req["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert req["betas"] == [FALLBACK_BETA] and req["fallbacks"] == "default"
    assert not {"temperature", "top_p", "top_k", "thinking", "tool_choice"} & set(req)  # rejected by this model
    assert req["messages"][0]["role"] == "user" and '"asof": "2026-10-25"' in req["messages"][0]["content"]


def test_fallbacks_can_be_turned_off(digest):
    req = build_request(digest, "p", fallbacks=False)
    assert "betas" not in req and "fallbacks" not in req


def test_schema_matches_the_prompt_output_format():
    assert list(SCHEMA["properties"]) == ["status", "validationSummary", "metricsSummary", "executiveSummary", "publishRecommendation"]
    assert list(SCHEMA["properties"]["validationSummary"]["properties"]) == ["missingValues", "duplicateRecords", "dataQualityIssues"]
    assert list(SCHEMA["properties"]["metricsSummary"]["properties"]) == ["requirements", "risks", "actions", "overallHealth"]


# --- running ------------------------------------------------------------------

def test_run_agent_returns_the_assessment(digest):
    client = FakeClient()
    result = run_agent(digest, client=client, prompt="p")
    assert result.assessment == GOOD and result.error is None and result.request_id == "req_1"
    assert len(client.calls) == 1


def test_run_agent_without_fallbacks_uses_plain_endpoint(digest):
    client = FakeClient()
    run_agent(digest, client=client, prompt="p", fallbacks=False)
    assert "betas" not in client.calls[0]


@pytest.mark.parametrize("response, expect", [
    (reply(stop_reason="refusal"), "refusal"),
    (reply(stop_reason="max_tokens"), "max_tokens"),
    (reply(text="not json"), "not valid JSON"),
    (reply(text=json.dumps({**GOOD, "status": "MAYBE"})), "status"),
    (reply(text=json.dumps({**GOOD, "executiveSummary": ["only one"]})), "executiveSummary"),
    (reply(text=json.dumps({**GOOD, "publishRecommendation": " "})), "publishRecommendation"),
])
def test_unusable_answers_become_errors(digest, response, expect):
    result = run_agent(digest, client=FakeClient(response), prompt="p")
    assert result.assessment is None and expect in result.error
    assert result.status == "FAIL"


def test_api_error_becomes_an_error_result(digest):
    result = run_agent(digest, client=FakeClient(exc=anthropic.APIError("boom", request=None, body=None)), prompt="p")
    assert result.assessment is None and "boom" in result.error


def test_check_assessment_accepts_good_answer():
    assert check_assessment(GOOD) is None


# --- gate ---------------------------------------------------------------------

def clean():
    return Report().to_dict()


def with_warning():
    rep = Report()
    rep.warn("Workshops", 2, "Epic IDs", "x")
    return rep.to_dict()


def with_error():
    rep = Report()
    rep.error("Workshops", 2, None, "x")
    return rep.to_dict()


def test_gate_passes_through_agent_status():
    assert gate(AgentResult({**GOOD, "status": "PASS"}), clean()) == {"status": "PASS", "publish": True, "reason": "agent assessment"}


def test_gate_never_lowers_status_below_workbook_warnings():
    d = gate(AgentResult({**GOOD, "status": "PASS"}), with_warning())
    assert d["status"] == "WARNING" and d["publish"] and "raised" in d["reason"]


def test_gate_blocks_on_agent_fail():
    assert gate(AgentResult({**GOOD, "status": "FAIL"}), clean())["publish"] is False


def test_gate_blocks_on_workbook_errors_even_if_agent_passes():
    assert gate(AgentResult({**GOOD, "status": "PASS"}), with_error())["publish"] is False


def test_gate_fails_closed_when_agent_step_fails():
    d = gate(AgentResult(None, "boom"), clean())
    assert d["status"] == "FAIL" and d["publish"] is False and "boom" in d["reason"]


def test_gate_treats_a_skipped_agent_as_neutral():
    assert gate(AgentResult(None, skipped=True), clean())["status"] == "PASS"
    assert gate(AgentResult(None, skipped=True), with_warning())["status"] == "WARNING"


# --- claude CLI backend ---------------------------------------------------------

import subprocess

from datasync.agent import analyze, cli_command, parse_cli_output, run_agent_cli


def cli_proc(stdout="", returncode=0, stderr=""):
    return lambda *a, **kw: subprocess.CompletedProcess(a, returncode, stdout=stdout, stderr=stderr)


def envelope(**kw):
    return json.dumps({"type": "result", "is_error": False, "session_id": "sess_1", "total_cost_usd": 0.01, "usage": {"input_tokens": 5}, **kw})


def test_cli_command_is_tool_less_and_schema_bound():
    cmd = cli_command("PROMPT", "sonnet")
    assert cmd[:2] == ["claude", "-p"] and cmd[cmd.index("--system-prompt") + 1] == "PROMPT"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == SCHEMA
    assert cmd[cmd.index("--tools") + 1] == "" and "--bare" not in cmd  # --bare would skip the OAuth login


def test_cli_structured_output_is_used(digest):
    result = run_agent_cli(digest, prompt="p", runner=cli_proc(envelope(structured_output=GOOD)))
    assert result.assessment == GOOD and result.request_id == "sess_1" and result.usage["total_cost_usd"] == 0.01


def test_cli_fenced_text_answer_is_accepted(digest):
    text = "```json\n" + json.dumps(GOOD) + "\n```"
    assert run_agent_cli(digest, prompt="p", runner=cli_proc(envelope(result=text))).assessment == GOOD


def test_cli_event_list_uses_last_result_event():
    out = json.dumps([{"type": "system"}, json.loads(envelope(structured_output=GOOD))])
    assert parse_cli_output(out)[0] == GOOD


@pytest.mark.parametrize("proc, expect", [
    (cli_proc("", returncode=1, stderr="boom"), "exited 1"),
    (cli_proc("not json"), "not JSON"),
    (cli_proc(envelope(is_error=True, result="Invalid API key")), "Invalid API key"),
    (cli_proc(envelope(result="free text")), "not valid JSON"),
    (cli_proc(envelope(structured_output={**GOOD, "status": "MAYBE"})), "status"),
])
def test_cli_failures_become_errors(digest, proc, expect):
    result = run_agent_cli(digest, prompt="p", runner=proc)
    assert result.assessment is None and expect in result.error and result.status == "FAIL"


def test_cli_missing_binary_and_timeout_become_errors(digest):
    def missing(*a, **kw):
        raise FileNotFoundError("claude")

    def slow(*a, **kw):
        raise subprocess.TimeoutExpired("claude", 1)

    assert "FileNotFoundError" in run_agent_cli(digest, prompt="p", runner=missing).error
    assert "TimeoutExpired" in run_agent_cli(digest, prompt="p", runner=slow).error


def test_cli_digest_goes_through_stdin_not_argv(digest):
    seen = {}

    def runner(cmd, **kw):
        seen.update(cmd=cmd, input=kw["input"])
        return subprocess.CompletedProcess(cmd, 0, stdout=envelope(structured_output=GOOD), stderr="")

    run_agent_cli(digest, prompt="p", runner=runner)
    assert '"asof": "2026-10-25"' in seen["input"] and not any("asof" in a for a in seen["cmd"])


def test_analyze_picks_backend(digest, monkeypatch):
    monkeypatch.delenv("DATASYNC_AGENT_BACKEND", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert analyze(digest, client=FakeClient(), prompt="p").assessment == GOOD  # a client means the api backend
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr("datasync.agent.run_agent_cli", lambda d, **kw: AgentResult(GOOD, model="cli"))
    assert analyze(digest).model == "cli"  # the token alone selects the cli backend
    with pytest.raises(ValueError):
        analyze(digest, backend="nope")
