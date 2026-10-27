import json

import pytest

from datasync.digest import build_digest
from datasync.excel_to_model import Report
from datasync.report_email import render_email
from datasync.run_refresh import main, merge_history, previous_digest, run_refresh
from datasync.workbook_writer import write_workbook
from test_agent import GOOD, FakeClient, reply
from test_excel_to_model import edit, tiny_payload


@pytest.fixture
def env(tmp_path):
    payload = tiny_payload()
    book = tmp_path / "book.xlsx"
    write_workbook(payload, book)
    return book, tmp_path / "out", tmp_path / "state"


def answer(**changes):
    return FakeClient(reply(text=json.dumps({**GOOD, **changes})))


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_publishes_and_updates_state(env):
    book, out, state = env
    s = run_refresh(book, out, state, client=answer(status="PASS"))
    assert s["status"] == "PASS" and s["publish"] and s["published_files"] == ["cockpit.html", "cockpit_data.json"]
    assert "Phoenix R6 Program Cockpit" in (out / "cockpit.html").read_text(encoding="utf-8")
    assert read(out / "cockpit_data.json")["data"]["W"][0][0] == "200"
    assert (state / "digests" / "2026-10-25.json").exists()
    assert read(state / "burnup_history.json") == {"2026-10-26": []}  # no completed PBIs in the tiny workbook
    assert read(out / "email.json")["subject"] == "[Phoenix R6 Program Cockpit] PASS - data as of 2026-10-25"


def test_agent_fail_blocks_publishing_and_state(env):
    book, out, state = env
    s = run_refresh(book, out, state, client=answer(status="FAIL"))
    assert not s["publish"] and s["published_files"] == []
    assert not (out / "cockpit.html").exists() and not (out / "cockpit_data.json").exists()
    assert not state.exists() or not any(state.rglob("*.json"))  # a bad run never becomes the baseline
    assert read(out / "email.json")["subject"].endswith("FAIL - data as of 2026-10-25 - NOT published")


def test_agent_error_fails_closed_but_still_sends_gaps(env):
    book, out, state = env
    s = run_refresh(book, out, state, client=FakeClient(reply(stop_reason="refusal")))
    assert not s["publish"] and "refusal" in s["reason"]
    html = (out / "email.html").read_text(encoding="utf-8")
    assert "No AI insights this run" in html and "Gaps that need attention" in html


def test_no_agent_publishes_on_workbook_validation_alone(env):
    book, out, state = env
    s = run_refresh(book, out, state, use_agent=False)
    assert s["publish"] and not s["agent_used"] and s["model"] is None
    assert "agent step skipped" in s["reason"]


def test_workbook_errors_stop_everything_and_email_the_errors(env):
    book, out, state = env
    edit(book, "L4_Epics", "Epic ID", 2, "100")  # duplicate id
    s = run_refresh(book, out, state, client=FakeClient())
    assert not s["publish"] and s["status"] == "FAIL" and "workbook failed validation" in s["reason"]
    assert not (out / "digest.json").exists() and not (out / "cockpit.html").exists()
    assert "duplicate id 100" in (out / "email.txt").read_text(encoding="utf-8")


def test_stale_dashboard_is_removed_when_a_run_does_not_publish(env):
    book, out, state = env
    out.mkdir(parents=True)
    (out / "cockpit.html").write_text("yesterday", encoding="utf-8")
    run_refresh(book, out, state, client=answer(status="FAIL"))
    assert not (out / "cockpit.html").exists()


def test_second_day_compares_with_the_stored_digest(env):
    book, out, state = env
    run_refresh(book, out, state, use_agent=False)
    assert read(out / "digest.json")["kpi_changes"] is None
    edit(book, "Meta", "Value", 1, "2026-10-26")  # asof
    run_refresh(book, out, state, use_agent=False)
    d = read(out / "digest.json")
    assert d["previous_asof"] == "2026-10-25" and d["kpi_changes"] is not None


def test_same_day_rerun_does_not_compare_with_itself(env):
    book, out, state = env
    run_refresh(book, out, state, use_agent=False)
    run_refresh(book, out, state, use_agent=False)
    assert read(out / "digest.json")["previous_asof"] is None


def test_burnup_history_merges_seed_workbook_and_state(env):
    book, out, state = env
    (state).mkdir()
    (state / "burnup_history.json").write_text(json.dumps({"2026-10-19": ["600"]}), encoding="utf-8")
    run_refresh(book, out, state, use_agent=False)
    hist = read(out / "cockpit_data.json")["burnup_history"]
    assert set(hist) == {"2026-10-18", "2026-10-19"} and hist["2026-10-19"] == ["600"]
    assert len(hist["2026-10-18"]) == 19 and hist["2026-10-18"][-1] == "600"  # 18 from the committed seed + 1 from the workbook


def test_merge_history_unions_ids_per_date():
    merged = merge_history({"2026-10-18": ["1", "2"]}, {"2026-10-18": ["2", "3"], "2026-10-11": ["9"]})
    assert merged == {"2026-10-11": ["9"], "2026-10-18": ["1", "2", "3"]}


def test_previous_digest_picks_newest_earlier_date(tmp_path):
    for day in ("2026-10-11", "2026-10-18", "2026-10-25"):
        (tmp_path / "digests").mkdir(exist_ok=True)
        (tmp_path / "digests" / f"{day}.json").write_text(json.dumps({"asof": day}), encoding="utf-8")
    assert previous_digest(tmp_path, "2026-10-25")["asof"] == "2026-10-18"
    assert previous_digest(tmp_path, "2026-10-11") is None


def test_cli_exit_codes(env, tmp_path):
    book, out, state = env
    assert main([str(book), "--out-dir", str(out), "--state-dir", str(state), "--no-agent"]) == 0
    edit(book, "L4_Epics", "Epic ID", 2, "100")
    assert main([str(book), "--out-dir", str(out), "--state-dir", str(state), "--no-agent"]) == 1


# --- email --------------------------------------------------------------------

def email_run(**over):
    digest = build_digest(tiny_payload(), Report().to_dict())
    base = {"title": "T", "asof": "2026-10-25", "decision": {"status": "WARNING", "publish": True, "reason": "agent assessment"},
            "assessment": GOOD, "agent_error": None, "digest": digest, "report": Report().to_dict(),
            "ado_url": "https://ado.example/_workitems/edit/", "counts": {"E": 2}}
    return {**base, **over}


def test_email_escapes_model_text():
    evil = {**GOOD, "executiveSummary": ["<script>alert(1)</script>", "b", "c"], "publishRecommendation": "<b>x</b>"}
    out = render_email(email_run(assessment=evil))
    assert "<script>" not in out["html"] and "&lt;script&gt;" in out["html"] and "<b>x</b>" not in out["html"]


def test_email_links_record_ids_to_ado():
    out = render_email(email_run())
    assert 'href="https://ado.example/_workitems/edit/' in out["html"]


def test_email_subject_flags_unpublished_runs():
    out = render_email(email_run(decision={"status": "FAIL", "publish": False, "reason": "x"}))
    assert out["subject"] == "[T] FAIL - data as of 2026-10-25 - NOT published" and out["publish"] is False


def test_email_recipients_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("DATASYNC_EMAIL_TO", "a@x.com; b@x.com")
    monkeypatch.setenv("DATASYNC_EMAIL_CC", "")
    out = render_email(email_run())
    assert out["to"] == ["a@x.com", "b@x.com"] and out["cc"] == []


def test_email_without_digest_lists_workbook_errors():
    rep = Report()
    rep.error("PBIs", 7, "PBI ID", "blank id")
    out = render_email(email_run(digest=None, assessment=None, report=rep.to_dict(), decision={"status": "FAIL", "publish": False, "reason": "r"}))
    assert "PBIs row 7: blank id" in out["text"]
