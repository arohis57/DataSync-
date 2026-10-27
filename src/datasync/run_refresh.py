"""One refresh: workbook -> payload -> digest -> agent -> publish decision -> dashboard + email report.

Usage:  python -m datasync.run_refresh WORKBOOK.xlsx [--out-dir DIR] [--state-dir DIR] [--no-agent]

Everything the run produces goes to --out-dir (cockpit.html and cockpit_data.json only when the
decision is to publish; the email and run files every time). What carries over between runs goes
to --state-dir: past digests (for trends) and burn-up snapshots. State is updated only after a
run that publishes, so a bad refresh never becomes the baseline for the next one.

Exit code: 0 published (PASS or WARNING), 1 not published.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from .agent import AgentResult, analyze, gate
from .digest import build_digest, records
from .excel_to_model import DEFAULT_CONFIG, ROOT, build_payload
from .report_email import render_email

log = logging.getLogger("datasync")

BURNUP_SEED = ROOT / "config" / "burnup_history_seed.json"
PUBLISH_FILES = ("cockpit.html", "cockpit_data.json")


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def _load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def merge_history(*sources: dict[str, list[str]]) -> dict[str, list[str]]:
    """Union of burn-up snapshots per date, keeping first-seen order."""
    merged: dict[str, list[str]] = {}
    for src in sources:
        for day, ids in src.items():
            seen = merged.setdefault(day, [])
            seen.extend(i for i in ids if i not in seen)
    return dict(sorted(merged.items()))


def previous_digest(state_dir: Path, asof: str) -> dict | None:
    """The newest stored digest from an earlier reporting date (a same-day re-run compares with the day before)."""
    earlier = sorted(p for p in (state_dir / "digests").glob("*.json") if p.stem < asof)
    return json.loads(earlier[-1].read_text(encoding="utf-8")) if earlier else None


def render_dashboard(payload: dict) -> str:
    spec = importlib.util.spec_from_file_location("generate_cockpit", ROOT / "src" / "cockpit" / "generate_cockpit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.render(mod.TEMPLATE, payload)


def run_refresh(workbook: Path, out_dir: Path, state_dir: Path, *, config_path: Path = DEFAULT_CONFIG,
                use_agent: bool = True, client=None, **agent_opts) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in PUBLISH_FILES:  # never leave a previous run's dashboard where the publisher would pick it up
        (out_dir / name).unlink(missing_ok=True)

    log.info("reading %s", workbook)
    payload, rep = build_payload(workbook, config_path)
    report = rep.to_dict()
    _dump(out_dir / "validation_report.json", report)

    digest, result, assessment_error = None, None, None
    if payload is None:
        log.error("workbook failed validation (%d error(s))", len(rep.errors))
        decision = {**gate(AgentResult(None, skipped=True), report), "reason": f"workbook failed validation ({len(rep.errors)} error(s))"}
        title, asof, counts, ado_url = "Program Cockpit", "unknown", {}, ""
        try:
            title = json.loads(config_path.read_text(encoding="utf-8"))["title"]
        except (OSError, KeyError, ValueError):
            pass
    else:
        title, asof, counts, ado_url = payload["title"], payload["asof"], rep.counts, payload.get("ado_workitem_url", "")
        payload["burnup_history"] = merge_history(_load(BURNUP_SEED, {}), payload["burnup_history"], _load(state_dir / "burnup_history.json", {}))
        digest = build_digest(payload, report, previous_digest(state_dir, asof))
        _dump(out_dir / "digest.json", digest)
        if use_agent:
            log.info("asking the agent")
            result = analyze(digest, client=client, **agent_opts)
        else:
            result = AgentResult(None, None, skipped=True)
        decision = gate(result, report)
        assessment_error = result.error
        _dump(out_dir / "agent_result.json", {"decision": decision, "assessment": result.assessment, "error": result.error,
                                              "request_id": result.request_id, "model": result.model, "usage": result.usage})

    email = render_email({"title": title, "asof": asof, "decision": decision, "assessment": result.assessment if result else None,
                          "agent_error": assessment_error, "digest": digest, "report": report, "ado_url": ado_url, "counts": counts})
    (out_dir / "email.html").write_text(email["html"], encoding="utf-8")
    (out_dir / "email.txt").write_text(email["text"], encoding="utf-8")
    _dump(out_dir / "email.json", {k: email[k] for k in ("subject", "status", "publish", "to", "cc")})

    published: list[str] = []
    if decision["publish"]:
        (out_dir / "cockpit.html").write_text(render_dashboard(payload), encoding="utf-8", newline="")
        _dump(out_dir / "cockpit_data.json", payload)
        published = list(PUBLISH_FILES)
        _dump(state_dir / "digests" / f"{asof}.json", digest)
        completed = [r["PBI ID"] for r in records(payload, "P") if r["State"] == "Completed"]
        history = _load(state_dir / "burnup_history.json", {})
        history[payload["burnup_latest_export"]] = completed  # a re-run on the same export replaces its snapshot
        _dump(state_dir / "burnup_history.json", history)
        log.info("published: %s", ", ".join(published))
    else:
        log.warning("NOT published: %s", decision["reason"])

    summary = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "workbook": str(workbook), "asof": asof,
               **decision, "published_files": published, "counts": counts, "agent_used": bool(use_agent and payload is not None),
               "model": result.model if result else None, "request_id": result.request_id if result else None,
               "usage": result.usage if result else None}
    _dump(out_dir / "run_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run one DataSync refresh.")
    ap.add_argument("workbook", type=Path)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "build")
    ap.add_argument("--state-dir", type=Path, default=ROOT / "state")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--no-agent", action="store_true", help="skip the AI step; decide on workbook validation only")
    ap.add_argument("--model", help="api backend: model id; cli backend: alias such as sonnet")
    ap.add_argument("--no-fallbacks", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)

    summary = run_refresh(args.workbook, args.out_dir, args.state_dir, config_path=args.config, use_agent=not args.no_agent,
                          fallbacks=not args.no_fallbacks, **({"model": args.model} if args.model else {}))
    print(f"{summary['status']}: {summary['reason']} (publish={summary['publish']}) -> {args.out_dir}")
    return 0 if summary["publish"] else 1


if __name__ == "__main__":
    sys.exit(main())
