"""Read the DataSync workbook and build the payload the cockpit generator renders.

Usage:  python -m datasync.excel_to_model WORKBOOK.xlsx [-o OUT.json] [--config CFG.json] [--report REPORT.json]

Errors (missing sheet/column, duplicate or blank ids) stop the run and nothing is written.
Warnings (dangling links, bad dates) are dropped/blanked in the payload and listed in the
report so the validation step can see them.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import range_boundaries

from .schema import (
    ACTION_LINKS,
    BURNUP_HEADERS,
    BURNUP_SHEET,
    BURNUP_TABLE,
    META_KEYS,
    META_SHEET,
    META_TABLE,
    SHEETS,
    Col,
    Sheet,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "cockpit_config.json"
DEFAULT_OUT = ROOT / "build" / "cockpit_data.json"

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TRUE_TEXT = {"1", "y", "yes", "true", "x"}
FALSE_TEXT = {"", "0", "n", "no", "false"}


@dataclass
class Report:
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def error(self, sheet: str, row: int | None, column: str | None, message: str) -> None:
        self.errors.append({"sheet": sheet, "row": row, "column": column, "message": message})

    def warn(self, sheet: str, row: int | None, column: str | None, message: str) -> None:
        self.warnings.append({"sheet": sheet, "row": row, "column": column, "message": message})

    def to_dict(self) -> dict:
        return {"ok": not self.errors, "counts": self.counts, "errors": self.errors, "warnings": self.warnings}


Row = tuple[int, dict[str, Any]]  # (Excel row number, {header: cell value})


def read_table(wb, sheet: str, table: str, headers: list[str], rep: Report) -> list[Row] | None:
    """Rows of one Excel table, or None (with errors recorded) if it can't be read."""
    if sheet not in wb.sheetnames:
        rep.error(sheet, None, None, f"sheet '{sheet}' not found")
        return None
    ws = wb[sheet]
    tbl = ws.tables.get(table)
    if tbl is None:
        rep.error(sheet, None, None, f"Excel table '{table}' not found on sheet '{sheet}'")
        return None
    min_col, min_row, max_col, max_row = range_boundaries(tbl.ref)
    rows = ws.iter_rows(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col, values_only=True)
    found = [str(h).strip() if h is not None else "" for h in next(rows)]
    missing = [h for h in headers if h not in found]
    if missing:
        rep.error(sheet, min_row, None, f"table '{table}' is missing column(s): {', '.join(missing)}")
        return None
    out: list[Row] = []
    for n, values in enumerate(rows, start=min_row + 1):
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in values):
            continue
        out.append((n, dict(zip(found, values))))
    return out


def norm_id(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def norm_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def norm_date(v: Any) -> str | None:
    """ISO date string, None when blank, ValueError when not a date."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()[:10]
    if ISO_DATE.match(s):
        date.fromisoformat(s)  # rejects 2026-13-45
        return s
    raise ValueError(f"not a date: {v!r}")


def norm_flag(v: Any) -> int:
    s = str(v).strip().lower() if v is not None else ""
    if s in TRUE_TEXT or (isinstance(v, (int, float)) and v):
        return 1
    if s in FALSE_TEXT or s in {"0.0"}:
        return 0
    raise ValueError(f"not a 0/1 flag: {v!r}")


def split_ids(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (int, float)):
        return [norm_id(v)]
    return [norm_id(p) for p in re.split(r"[;,]", str(v)) if p.strip()]


def build_index(spec: Sheet, rows: list[Row], rep: Report) -> dict[str, int]:
    """id -> position in the payload array (row order is preserved)."""
    key = next(c for c in spec.cols if c.kind in ("id", "key_opt"))
    index: dict[str, int] = {}
    for pos, (n, r) in enumerate(rows):
        kid = norm_id(r[key.header])
        if not kid:
            if key.kind == "id":
                rep.error(spec.sheet, n, key.header, "blank id")
            continue
        if kid in index:
            rep.error(spec.sheet, n, key.header, f"duplicate id {kid} (also row {rows[index[kid]][0]})")
            continue
        index[kid] = pos
    return index


def convert_row(spec: Sheet, n: int, r: dict[str, Any], indexes: dict[str, dict[str, int]], rep: Report) -> list[Any]:
    out: list[Any] = []
    for col in spec.cols:
        if col.kind == "derived":
            out.append(None)  # filled in by finish_derived
            continue
        raw = r[col.header]
        try:
            out.append(convert_cell(col, raw, spec, n, indexes, rep))
        except ValueError as e:
            rep.warn(spec.sheet, n, col.header, f"{e}; value cleared")
            out.append(None if col.kind == "date" else 0 if col.kind == "flag" else "")
    return out


def convert_cell(col: Col, raw: Any, spec: Sheet, n: int, indexes: dict[str, dict[str, int]], rep: Report) -> Any:
    kind = col.kind
    if kind in ("id", "key_opt"):
        return norm_id(raw)
    if kind == "text":
        return norm_text(raw)
    if kind == "date":
        return norm_date(raw)
    if kind == "flag":
        return norm_flag(raw)
    target = indexes[col.target]
    if kind == "ids":
        resolved: list[int] = []
        for i in split_ids(raw):
            if i not in target:
                rep.warn(spec.sheet, n, col.header, f"{col.target} id {i} not found; link dropped")
            elif target[i] in resolved:
                rep.warn(spec.sheet, n, col.header, f"id {i} listed twice; duplicate dropped")
            else:
                resolved.append(target[i])
        return resolved
    if kind == "ref":
        i = norm_id(raw)
        if not i:
            return -1
        if i not in target:
            rep.warn(spec.sheet, n, col.header, f"{col.target} id {i} not found; treated as no parent")
            return -1
        return target[i]
    raise ValueError(f"unknown column kind {kind}")


def finish_derived(spec: Sheet, rows: list[list[Any]]) -> None:
    if spec.key != "P":
        return
    ref_pos = next(i for i, c in enumerate(spec.cols) if c.kind == "ref")
    derived_pos = next(i for i, c in enumerate(spec.cols) if c.kind == "derived")
    for row in rows:
        row[derived_pos] = "N" if row[ref_pos] < 0 else ""


def read_meta(wb, rep: Report) -> dict[str, str]:
    rows = read_table(wb, META_SHEET, META_TABLE, ["Key", "Value"], rep)
    meta: dict[str, str] = {}
    for n, r in rows or []:
        meta[norm_id(r["Key"])] = r["Value"]
    out: dict[str, str] = {}
    for key in META_KEYS if rows is not None else ():
        if key not in meta:
            rep.error(META_SHEET, None, "Key", f"missing setting '{key}'")
            continue
        try:
            d = norm_date(meta[key])
        except ValueError as e:
            rep.error(META_SHEET, None, "Value", f"{key}: {e}")
            continue
        if d is None:
            rep.error(META_SHEET, None, "Value", f"{key} is blank")
        else:
            out[key] = d
    return out


def read_burnup(wb, rep: Report) -> dict[str, list[str]]:
    """Snapshots stored in the workbook. The sheet is optional: the refresh keeps its own history."""
    if BURNUP_SHEET not in wb.sheetnames:
        return {}
    rows = read_table(wb, BURNUP_SHEET, BURNUP_TABLE, list(BURNUP_HEADERS), rep)
    hist: dict[str, list[str]] = {}
    for n, r in rows or []:
        try:
            d = norm_date(r["Snapshot Date"])
        except ValueError as e:
            rep.warn(BURNUP_SHEET, n, "Snapshot Date", f"{e}; row skipped")
            continue
        pid = norm_id(r["PBI ID"])
        if d is None or not pid:
            rep.warn(BURNUP_SHEET, n, None, "blank snapshot date or PBI ID; row skipped")
            continue
        hist.setdefault(d, []).append(pid)
    return hist


def build_payload(workbook: Path, config_path: Path = DEFAULT_CONFIG) -> tuple[dict | None, Report]:
    rep = Report()
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    wb = load_workbook(workbook, data_only=True)

    tables: dict[str, list[Row]] = {}
    for spec in SHEETS:
        rows = read_table(wb, spec.sheet, spec.table, [c.header for c in spec.cols if c.header], rep)
        if rows is not None:
            tables[spec.key] = rows
    links = read_table(wb, ACTION_LINKS.sheet, ACTION_LINKS.table, [c.header for c in ACTION_LINKS.cols], rep)
    meta = read_meta(wb, rep)
    burnup = read_burnup(wb, rep)
    if rep.errors:
        return None, rep

    indexes = {spec.key: build_index(spec, tables[spec.key], rep) for spec in SHEETS}
    if rep.errors:
        return None, rep

    data: dict[str, list] = {}
    for spec in SHEETS:
        converted = [convert_row(spec, n, r, indexes, rep) for n, r in tables[spec.key]]
        finish_derived(spec, converted)
        data[spec.key] = converted
        rep.counts[spec.key] = len(converted)

    data["AL"] = []
    workshop_ids = indexes["W"]
    for n, r in links or []:
        raid_id, ws_id = norm_id(r["RAID ID"]), norm_id(r["Workshop ID"])
        if not raid_id or not ws_id:
            rep.warn(ACTION_LINKS.sheet, n, None, "blank RAID ID or Workshop ID; row skipped")
            continue
        if ws_id not in workshop_ids:
            rep.warn(ACTION_LINKS.sheet, n, "Workshop ID", f"workshop {ws_id} not found; dashboard will ignore this link")
        data["AL"].append([raid_id, ws_id])
    rep.counts["AL"] = len(data["AL"])

    if rep.errors:
        return None, rep
    payload = {**config, **meta, "burnup_history": burnup, "data": data}
    return payload, rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the cockpit payload from the DataSync workbook.")
    ap.add_argument("workbook", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--report", type=Path, help="default: validation_report.json next to --out")
    args = ap.parse_args(argv)

    payload, rep = build_payload(args.workbook, args.config)
    report_path = args.report or args.out.with_name("validation_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(rep.to_dict(), indent=1, ensure_ascii=False), encoding="utf-8")

    for e in rep.errors:
        print(f"ERROR   {e['sheet']} row {e['row']} [{e['column']}]: {e['message']}", file=sys.stderr)
    if payload is None:
        print(f"{len(rep.errors)} error(s); nothing written. Report: {report_path}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    counts = ", ".join(f"{k}={v}" for k, v in rep.counts.items())
    print(f"wrote {args.out} ({counts}); {len(rep.warnings)} warning(s). Report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
