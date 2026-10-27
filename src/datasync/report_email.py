"""Render the refresh report email (gaps, insights, publish decision).

The orchestrator writes the result to disk; Power Automate (or any mailer) sends it. Gaps come from
the digest, which is computed in code, so the email is useful even when the agent step fails or is
skipped. Anything the model wrote is HTML-escaped.
"""
from __future__ import annotations

import os
from html import escape
from typing import Any

COLORS = {"PASS": "#1E8E5E", "WARNING": "#C27C00", "FAIL": "#C8323F"}
MAX_IDS = 6


def _recipients(var: str) -> list[str]:
    return [a.strip() for a in os.environ.get(var, "").split(";") if a.strip()]


def gap_rows(digest: dict | None, report: dict) -> list[dict]:
    """[{area, issue, count, ids}] for everything that needs a person to look."""
    rows: list[dict] = []

    def add(area: str, issue: str, count: int, ids: list[str] | None = None) -> None:
        if count:
            rows.append({"area": area, "issue": issue, "count": count, "ids": list(ids or [])[:MAX_IDS]})

    for e in report.get("errors", []):
        add("Workbook", f"{e['sheet']} row {e['row']}: {e['message']}", 1)
    if digest is None:
        return rows
    dq = digest["data_quality"]
    for g in dq["warning_groups"]:
        add("Workbook", f"{g['sheet']}: {g['issue']}", g["count"])
    for m in dq["missing_values"]:
        add("Missing values", f"{m['entity']} with no {m['field']} (of {m['of']})", m["count"], m["sample_ids"])
    for x in dq["duplicate_records"]:
        add("Duplicates", f"{x['entity']}: records sharing a title within a workstream ({x['duplicate_groups']} groups)",
            x["records_involved"], [i for grp in x["sample_groups"] for i in grp])
    for x in dq["status_inconsistencies"]:
        add("Inconsistent status", x["issue"], x["count"], x["sample_ids"])
    t = digest["traceability"]
    add("Traceability", "Requirements with no L4 epic", t["without_l4_epic"])
    for label, key in (("Build items with no requirement", "build_items_without_requirement"),
                       ("Build items with no PBI", "build_items_without_pbi"), ("PBIs with no parent build item", "pbis_without_parent")):
        add("Traceability", label, t[key]["count"], t[key]["sample_ids"])
    add("Delivery", "PBIs blocked", digest["pbis"]["blocked"]["count"], digest["pbis"]["blocked"]["sample_ids"])
    k = digest["kdds"]["open_past_target"]
    add("Delivery", "KDDs open past target date", k["count"], k["sample_ids"])
    w = digest["workshops"]["not_completed_past_target"]
    add("Delivery", "Workshops not completed past target date", w["count"], w["sample_ids"])
    r = digest["raid"]
    add("RAID", "Open items past due", r["past_due"], r["oldest_overdue_ids"])
    add("RAID", "Open RAID-Critical risks and issues", r["critical_open"], r["critical_open_ids"])
    return rows


def render_email(run: dict) -> dict:
    """run: title, asof, decision{status,publish,reason}, assessment|None, agent_error|None, digest|None, report, ado_url, counts"""
    d, a = run["decision"], run.get("assessment")
    status, color = d["status"], COLORS[d["status"]]
    title = run["title"]
    subject = f"[{title}] {status} - data as of {run['asof']}" + ("" if d["publish"] else " - NOT published")
    gaps = gap_rows(run.get("digest"), run["report"])
    link = run.get("ado_url") or ""

    def ids_html(ids: list[str]) -> str:
        return ", ".join(f'<a href="{escape(link + i)}">{escape(i)}</a>' if link else escape(i) for i in ids)

    def bullets(items: list[str]) -> str:
        return "<ul style='margin:6px 0 0 18px;padding:0'>" + "".join(f"<li style='margin:3px 0'>{escape(x)}</li>" for x in items) + "</ul>"

    h2 = "font:700 15px Segoe UI,Arial,sans-serif;margin:22px 0 4px;color:#0E1B3D"
    p = "font:14px/1.45 Segoe UI,Arial,sans-serif;margin:4px 0;color:#0E1B3D"
    parts = [
        f"<div style='max-width:760px;font-family:Segoe UI,Arial,sans-serif;color:#0E1B3D'>",
        f"<div style='background:{color};color:#fff;padding:12px 16px;border-radius:6px'>"
        f"<div style='font:700 18px Segoe UI,Arial,sans-serif'>{escape(title)}: {status}</div>"
        f"<div style='font:13px Segoe UI,Arial,sans-serif;margin-top:2px'>Data as of {escape(run['asof'])} - "
        f"{'published' if d['publish'] else 'NOT published'} - {escape(d['reason'])}</div></div>",
    ]
    if a:
        parts += [f"<h2 style='{h2}'>Executive summary</h2>{bullets(a['executiveSummary'])}"]
        m = a["metricsSummary"]
        parts += [f"<h2 style='{h2}'>Metrics</h2>"] + [
            f"<p style='{p}'><b>{label}:</b> {escape(m[key])}</p>"
            for label, key in (("Overall health", "overallHealth"), ("Requirements", "requirements"), ("Risks", "risks"), ("Actions", "actions"))]
        parts += [f"<h2 style='{h2}'>Publish recommendation</h2><p style='{p}'>{escape(a['publishRecommendation'])}</p>"]
    else:
        why = run.get("agent_error") or "the agent step was skipped"
        parts += [f"<p style='{p};margin-top:14px'><i>No AI insights this run: {escape(why)}. The gaps below were computed directly from the data.</i></p>"]

    parts += [f"<h2 style='{h2}'>Gaps that need attention ({len(gaps)})</h2>"]
    if gaps:
        th = "text-align:left;padding:5px 8px;border-bottom:2px solid #C9D2E0;font:600 12px Segoe UI,Arial,sans-serif;color:#6A7590"
        td = "padding:5px 8px;border-bottom:1px solid #DCE2EC;font:13px Segoe UI,Arial,sans-serif;vertical-align:top"
        parts += ["<table style='border-collapse:collapse;width:100%'><tr>"
                  f"<th style='{th}'>Area</th><th style='{th}'>Issue</th><th style='{th};text-align:right'>Count</th><th style='{th}'>Examples</th></tr>"]
        parts += [f"<tr><td style='{td}'>{escape(g['area'])}</td><td style='{td}'>{escape(g['issue'])}</td>"
                  f"<td style='{td};text-align:right'>{g['count']:,}</td><td style='{td}'>{ids_html(g['ids'])}</td></tr>" for g in gaps]
        parts += ["</table>"]
    else:
        parts += [f"<p style='{p}'>None found.</p>"]

    if a:
        v = a["validationSummary"]
        notes = [("Missing values", v["missingValues"]), ("Duplicate records", v["duplicateRecords"]), ("Data quality", v["dataQualityIssues"])]
        if any(items for _, items in notes):
            parts += [f"<h2 style='{h2}'>Agent's validation notes</h2>"]
            parts += [f"<p style='{p}'><b>{label}</b></p>{bullets(items)}" for label, items in notes if items]

    counts = ", ".join(f"{k} {v:,}" for k, v in run.get("counts", {}).items())
    parts += [f"<p style='font:12px Segoe UI,Arial,sans-serif;color:#6A7590;margin-top:22px'>Records read: {escape(counts)}. "
              "Generated by DataSync. AI-written text is based only on the computed digest.</p></div>"]

    text = [f"{title}: {status} - data as of {run['asof']} - {'published' if d['publish'] else 'NOT published'} ({d['reason']})", ""]
    if a:
        text += ["EXECUTIVE SUMMARY"] + [f"- {x}" for x in a["executiveSummary"]] + ["", f"Publish recommendation: {a['publishRecommendation']}", ""]
    else:
        text += [f"No AI insights this run: {run.get('agent_error') or 'the agent step was skipped'}.", ""]
    text += [f"GAPS ({len(gaps)})"] + [f"- [{g['area']}] {g['issue']}: {g['count']:,}" + (f" (e.g. {', '.join(g['ids'])})" if g["ids"] else "") for g in gaps]

    return {"subject": subject, "html": "".join(parts), "text": "\n".join(text), "status": status, "publish": d["publish"],
            "to": _recipients("DATASYNC_EMAIL_TO"), "cc": _recipients("DATASYNC_EMAIL_CC")}
