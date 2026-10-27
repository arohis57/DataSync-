"""Compact, deterministic summary of a payload for the DataSync agent.

The payload is ~2 MB of records, far too large to hand to a model, and counting is better done
in code than by a model. The digest holds the numbers, the data-quality signals and a few capped
samples of record ids; the agent turns it into a judgement and executive insights.

Person names are left out on purpose: the agent only needs ids, orgs and counts.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date
from typing import Any

from .schema import SHEETS

SAMPLE = 10  # max record ids listed per issue
KDD_CLOSED = {"Approved", "Rejected"}
ROW_NAMES = {s.key: [c.header or "_link_reason" for c in s.cols] for s in SHEETS}
SHEET_NAMES = {s.key: s.sheet for s in SHEETS}

DEFINITIONS = {
    "in_scope": "All records except Cancelled workshops and Rejected KDDs / requirements.",
    "planned_to_date": "In-scope records with a target date on or before asof.",
    "done": "Workshop Completed, KDD Approved, requirement Approved, PBI Completed.",
    "done_on_plan": "Done records whose target date is on or before asof.",
    "raid_open": "RAID items whose state is not in the closed states.",
    "raid_past_due": "Open RAID items with a target date before asof.",
    "raid_critical": "Open risks/issues tagged RAID-Critical (or listed in raid_critical_overrides).",
    "traceability_pct": "Share of Fit-Config / Gap requirements that link to at least one build item.",
}


def records(payload: dict, key: str) -> list[dict[str, Any]]:
    names = ROW_NAMES[key]
    return [dict(zip(names, row)) for row in payload["data"][key]]


def _pct(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


def _ids(rows: list[dict], id_col: str, limit: int = SAMPLE) -> list[str]:
    return [r[id_col] for r in rows[:limit]]


def _shape(message: str) -> str:
    """Collapse ids/numbers so identical problems group together."""
    return re.sub(r"\d+", "N", message)


def build_digest(payload: dict, report: dict, previous: dict | None = None) -> dict:
    asof = payload["asof"]
    asof_d = date.fromisoformat(asof)
    d = {k: records(payload, k) for k in ROW_NAMES}
    kpis: dict[str, float | int | None] = {}

    def planned(r: dict, col: str = "Target Date") -> bool:
        return bool(r[col]) and r[col] <= asof

    # --- progress by workstream -------------------------------------------------
    progress_spec = {  # key: (id col, state col, done state, excluded state)
        "W": ("Workshop ID", "State", "Completed", "Cancelled"),
        "K": ("KDD ID", "State", "Approved", "Rejected"),
        "Q": ("Requirement ID", "State", "Approved", "Rejected"),
        "P": ("PBI ID", "State", "Completed", None),
    }
    names = {"W": "workshops", "K": "kdds", "Q": "requirements", "P": "pbis"}
    progress: dict[str, dict] = {}
    for key, (_, st, done_state, excluded) in progress_spec.items():
        scope = [r for r in d[key] if r[st] != excluded]
        by_ws: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
        for r in scope:
            c = by_ws[r["Workstream"]]
            c["in_scope"] += 1
            c["planned_to_date"] += planned(r)
            c["done"] += r[st] == done_state
            c["done_on_plan"] += r[st] == done_state and planned(r)
        total = Counter()
        for c in by_ws.values():
            total.update(c)
        order = payload.get("workstream_order", [])
        ordered = sorted(by_ws, key=lambda w: (order.index(w) if w in order else len(order), w))
        progress[names[key]] = {"total": dict(total), "by_workstream": {w: dict(by_ws[w]) for w in ordered}}
        for m in ("in_scope", "planned_to_date", "done", "done_on_plan"):
            kpis[f"{names[key]}.{m}"] = total[m]
        kpis[f"{names[key]}.hit_rate_pct"] = _pct(total["done_on_plan"], total["planned_to_date"])

    # --- KDDs / workshops -------------------------------------------------------
    kdd_open_late = [r for r in d["K"] if r["State"] not in KDD_CLOSED and r["Target Date"] and r["Target Date"] < asof]
    ws_past = [r for r in d["W"] if r["State"] not in ("Completed", "Cancelled") and r["Target Date"] and r["Target Date"] < asof]
    kpis["kdds.open_past_target"] = len(kdd_open_late)
    kpis["workshops.not_completed_past_target"] = len(ws_past)

    # --- requirements and traceability -----------------------------------------
    reqs = [r for r in d["Q"] if r["State"] != "Rejected"]
    needs_build = [r for r in reqs if r["Disposition"] in ("FIT-CFG", "GAP")]
    with_build = [r for r in needs_build if r["Build Item IDs"]]
    kpis["requirements.traceability_pct"] = _pct(len(with_build), len(needs_build))
    kpis["requirements.without_l4_epic"] = sum(1 for r in reqs if not r["Epic IDs"])
    kpis["requirements.tbd_disposition"] = sum(1 for r in reqs if r["Disposition"] == "TBD")

    linked_builds = {i for r in reqs for i in r["Build Item IDs"]}
    pbi_parents = Counter(r["Build Item ID"] for r in d["P"] if r["Build Item ID"] >= 0)
    builds_no_req = [r for i, r in enumerate(d["C"]) if i not in linked_builds]
    builds_no_pbi = [r for i, r in enumerate(d["C"]) if i not in pbi_parents]
    pbi_orphans = [r for r in d["P"] if r["Build Item ID"] < 0]
    pbi_blocked = [r for r in d["P"] if r["State"] == "Blocked"]
    kpis["build_items.without_requirement"] = len(builds_no_req)
    kpis["build_items.without_pbi"] = len(builds_no_pbi)
    kpis["pbis.without_parent"] = len(pbi_orphans)
    kpis["pbis.blocked"] = len(pbi_blocked)

    # --- RAID --------------------------------------------------------------------
    closed = set(payload["raid_closed_states"])
    overrides = set(payload.get("raid_critical_overrides", []))
    open_raid = [r for r in d["R"] if r["State"] not in closed]
    past_due = [r for r in open_raid if r["Target Date"] and r["Target Date"] < asof]
    critical = [r for r in open_raid if r["Type"] in ("R", "I") and ("raid-critical" in r["Tags"].lower() or r["RAID ID"] in overrides)]
    by_firm: dict[str, Counter] = defaultdict(Counter)
    for r in open_raid:
        by_firm[r["Firm"] or "(none)"]["open"] += 1
    for r in past_due:
        by_firm[r["Firm"] or "(none)"]["past_due"] += 1
    overdue_days = sorted(((asof_d - date.fromisoformat(r["Target Date"])).days, r["RAID ID"]) for r in past_due)
    raid = {
        "open_by_type": dict(Counter(r["Type Name"] for r in open_raid)),
        "open": len(open_raid),
        "past_due": len(past_due),
        "past_due_by_type": dict(Counter(r["Type Name"] for r in past_due)),
        "critical_open": len(critical),
        "critical_open_ids": _ids(critical, "RAID ID"),
        "by_firm": {f: dict(c) for f, c in sorted(by_firm.items())},
        "oldest_overdue_days": overdue_days[-1][0] if overdue_days else 0,
        "oldest_overdue_ids": [i for _, i in overdue_days[-5:][::-1]],
        "state_counts": dict(Counter(r["State"] for r in d["R"])),
    }
    kpis.update({"raid.open": len(open_raid), "raid.past_due": len(past_due), "raid.critical_open": len(critical),
                 "raid.open_risks": raid["open_by_type"].get("Risk", 0), "raid.open_issues": raid["open_by_type"].get("Issue", 0),
                 "raid.open_actions": raid["open_by_type"].get("Action", 0)})

    # --- data quality ------------------------------------------------------------
    grouped: dict[tuple[str, str], dict] = {}
    for w in report.get("warnings", []):
        g = grouped.setdefault((w["sheet"], _shape(w["message"])), {"sheet": w["sheet"], "issue": _shape(w["message"]), "count": 0, "examples": []})
        g["count"] += 1
        if len(g["examples"]) < 3:
            g["examples"].append({"row": w["row"], "column": w["column"], "message": w["message"]})

    owner_col = {"Q": "Owner", "K": "Assigned To", "P": "Owner", "R": "Assigned To"}
    id_col = {"W": "Workshop ID", "K": "KDD ID", "Q": "Requirement ID", "C": "Build Item ID", "P": "PBI ID", "R": "RAID ID"}
    missing: list[dict] = []
    for key, entity in {"W": "workshops", "K": "kdds", "Q": "requirements", "C": "build_items", "P": "pbis", "R": "raid"}.items():
        scope = [r for r in d[key] if r.get("State") not in ("Cancelled", "Rejected") and (key != "R" or r["State"] not in closed)]
        checks = {"target date": [r for r in scope if not r["Target Date"]], "workstream": [r for r in scope if not r["Workstream"]]}
        if key in owner_col:
            checks["owner"] = [r for r in scope if not r[owner_col[key]]]
        for what, rows in checks.items():
            if rows:
                missing.append({"entity": entity, "field": what, "count": len(rows), "of": len(scope), "sample_ids": _ids(rows, id_col[key])})

    duplicates: list[dict] = []
    for key, entity in {"W": "workshops", "K": "kdds", "Q": "requirements", "R": "raid"}.items():
        seen: dict[tuple[str, str], list[str]] = defaultdict(list)
        for r in d[key]:
            if r.get("State") not in ("Cancelled", "Rejected") and r["Title"].strip():
                seen[(r["Workstream"], re.sub(r"\s+", " ", r["Title"]).strip().casefold())].append(r[id_col[key]])
        groups = [ids for ids in seen.values() if len(ids) > 1]
        if groups:
            duplicates.append({"entity": entity, "duplicate_groups": len(groups), "records_involved": sum(map(len, groups)),
                               "sample_groups": groups[:5]})

    inconsistencies: list[dict] = []
    kdd_states = set(payload.get("kdd_states", []))
    bad = [r for r in d["K"] if kdd_states and r["State"] not in kdd_states]
    if bad:
        inconsistencies.append({"issue": "KDD state not in the expected list", "count": len(bad), "sample_ids": _ids(bad, "KDD ID")})
    bad = [r for r in d["K"] if r["Approved Date"] and r["State"] != "Approved"]
    if bad:
        inconsistencies.append({"issue": "KDD has an approved date but is not Approved", "count": len(bad), "sample_ids": _ids(bad, "KDD ID")})
    bad = [r for r in d["K"] if r["State"] == "Approved" and not r["Approved Date"]]
    if bad:
        inconsistencies.append({"issue": "KDD is Approved but has no approved date", "count": len(bad), "sample_ids": _ids(bad, "KDD ID")})
    bad = [r for r in d["K"] if r["Date Flag"] == "C"]
    if bad:
        inconsistencies.append({"issue": "KDD target date is a placeholder to be checked", "count": len(bad), "sample_ids": _ids(bad, "KDD ID")})
    bad = [r for r in d["W"] if r["State"] == "Completed" and not r["Epic IDs"]]
    if bad:
        inconsistencies.append({"issue": "Completed workshop not linked to an L4 epic", "count": len(bad), "sample_ids": _ids(bad, "Workshop ID")})

    kpis["dq.workbook_warnings"] = len(report.get("warnings", []))
    kpis["dq.duplicate_groups"] = sum(x["duplicate_groups"] for x in duplicates)

    digest = {
        "asof": asof,
        "definitions": DEFINITIONS,
        "record_counts": report.get("counts", {}),
        "progress": progress,
        "traceability": {
            "requirements_in_scope": len(reqs),
            "by_disposition": dict(Counter(r["Disposition"] for r in reqs)),
            "needing_build_item": len(needs_build),
            "with_build_item": len(with_build),
            "traceability_pct": kpis["requirements.traceability_pct"],
            "without_l4_epic": kpis["requirements.without_l4_epic"],
            "no_workshop_flag": sum(r["No Workshop"] for r in reqs),
            "build_items_without_requirement": {"count": len(builds_no_req), "sample_ids": _ids(builds_no_req, "Build Item ID")},
            "build_items_without_pbi": {"count": len(builds_no_pbi), "sample_ids": _ids(builds_no_pbi, "Build Item ID")},
            "pbis_without_parent": {"count": len(pbi_orphans), "sample_ids": _ids(pbi_orphans, "PBI ID")},
        },
        "pbis": {"by_state": dict(Counter(r["State"] for r in d["P"])), "by_stage": dict(Counter(r["Stage"] for r in d["P"])),
                 "blocked": {"count": len(pbi_blocked), "sample_ids": _ids(pbi_blocked, "PBI ID")}},
        "kdds": {"by_state": dict(Counter(r["State"] for r in d["K"])),
                 "open_past_target": {"count": len(kdd_open_late), "sample_ids": _ids(kdd_open_late, "KDD ID")}},
        "workshops": {"by_state": dict(Counter(r["State"] for r in d["W"])),
                      "not_completed_past_target": {"count": len(ws_past), "sample_ids": _ids(ws_past, "Workshop ID")}},
        "raid": raid,
        "data_quality": {
            "workbook_errors": len(report.get("errors", [])),
            "workbook_warnings": len(report.get("warnings", [])),
            "warning_groups": sorted(grouped.values(), key=lambda g: -g["count"])[:15],
            "missing_values": missing,
            "duplicate_records": duplicates,
            "status_inconsistencies": inconsistencies,
        },
        "kpis": kpis,
    }
    if previous:
        prev = previous.get("kpis", {})
        digest["previous_asof"] = previous.get("asof")
        digest["kpi_changes"] = {k: {"previous": prev[k], "now": v, "change": round(v - prev[k], 1)}
                                 for k, v in kpis.items() if isinstance(v, (int, float)) and isinstance(prev.get(k), (int, float)) and v != prev[k]}
    else:
        digest["previous_asof"] = None
        digest["kpi_changes"] = None  # no history: the agent must not describe trends
    return digest
