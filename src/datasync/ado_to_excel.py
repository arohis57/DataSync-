"""
ADO Release 6 traceability extract (Python).

Creates 4 Excel files in a new folder next to this script:
  01  BPH L1 -> L2 -> L3 -> Epic (L4)           (BPH L4 used only to match Epics)
  02  Epic -> KDD / Requirements / Workshops / Build Items
  03  Requirement -> Build Items, Build Item -> PBI
  04  All RAID items (Risk, Issue, Action, Decision)

Cancelled items are excluded for every work item type.

Run:            python ado_r6_traceability.py
Rebuild only:   python ado_r6_traceability.py --use-cache
"""
import argparse
import base64
import datetime
import html
import json
import os
import re
import sys
import time
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

ORG_PROJECT = "Program-Phoenix/GFPhoenix"
ANALYTICS = "https://analytics.dev.azure.com/" + ORG_PROJECT + "/_odata/v4.0-preview/WorkItems"
WI_URL = "https://dev.azure.com/" + ORG_PROJECT + "/_workitems/edit/"
REST_WI = "https://dev.azure.com/" + ORG_PROJECT + "/_apis/wit/workitems"
R6 = "Custom_ReleasePlannedFor eq 'Release 6' and State ne 'Cancelled'"
LINKS = "Links($select=LinkTypeName;$expand=TargetWorkItem($select=WorkItemId,WorkItemType,Title,State))"
AREA = "Area($select=AreaPath)"
TAGS = "Tags($select=TagName)"
USER = "AssignedTo($select=UserName)"
AC_FIELD = "Microsoft.VSTS.Common.AcceptanceCriteria"
EXCLUDE_PBI_AREA = "GFPhoenix\\Change_OCM"
EXCLUDE_WS_TAG = "Signavio Process Flow"

START = time.time()


def log(msg):
    print("  [%4.0fs] %s" % (time.time() - START, msg), flush=True)


# ----------------------------------------------------------------- ADO access
class Ado(object):
    def __init__(self, pat):
        import truststore  # imported here so the row/workbook code works without the ADO-only packages
        import requests
        truststore.inject_into_ssl()
        token = base64.b64encode((":" + pat).encode("ascii")).decode("ascii")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": "Basic " + token})

    def get(self, url, tries=5):
        for attempt in range(1, tries + 1):
            try:
                r = self.s.get(url, timeout=300)
                r.raise_for_status()
                return r
            except Exception as e:
                print("  Attempt %d failed: %s" % (attempt, e), flush=True)
                if attempt == tries:
                    raise
                time.sleep(30 * attempt)

    def odata(self, flt, select, expand=None):
        url = ANALYTICS + "?$filter=" + quote(flt, safe="") + "&$select=" + select
        if expand:
            url = url + "&$expand=" + expand
        rows = []
        while url:
            data = self.get(url).json()
            rows.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        return rows

    def acceptance_criteria(self, ids):
        out = {}
        ids = [str(i) for i in ids]
        for start in range(0, len(ids), 200):
            batch = ids[start:start + 200]
            url = (REST_WI + "?ids=" + ",".join(batch) + "&fields=System.Id," + AC_FIELD
                   + "&errorPolicy=omit&api-version=7.1")
            for wi in self.get(url).json().get("value", []):
                if wi:
                    out[str(wi.get("id"))] = (wi.get("fields") or {}).get(AC_FIELD)
        return out


def find_field(metadata_xml, pattern, label):
    names = sorted(set(n for n in re.findall(r'Name="([^"]+)"', metadata_xml) if re.search(pattern, n)))
    print("  %s candidates: %s" % (label, ", ".join(names)))
    if not names:
        raise RuntimeError(label + " field not found in Analytics metadata.")
    return names[0]


def pull_all(ado):
    raw = {}
    log("Finding BPH field names in Analytics...")
    meta = ado.get(ANALYTICS.replace("/WorkItems", "") + "/$metadata").text
    raw["r6Field"] = find_field(meta, r"R6.*Align|Align.*R6", "R6 Aligned")
    raw["levelField"] = find_field(meta, r"BPH.*Level|Level.*PHX", "BPH Level PHX")
    r6f = raw["r6Field"]
    lvf = raw["levelField"]

    raw["reqs"] = ado.odata(
        "WorkItemType eq 'Requirement' and " + R6,
        "WorkItemId,Title,State,CreatedDate,TargetDate,Custom_ReleasePlannedFor,Custom_CapabilityGroup,"
        "Custom_ComplexTopic,Custom_Complexity,Custom_SolutionDispositionPHX",
        AREA + "," + USER)
    log("Requirements: %d" % len(raw["reqs"]))
    raw["ac"] = ado.acceptance_criteria([x["WorkItemId"] for x in raw["reqs"]])
    log("Acceptance Criteria pulled")

    raw["cfgs"] = ado.odata(
        "(WorkItemType eq 'Configuration' or WorkItemType eq 'RICEFW') and " + R6,
        "WorkItemId,WorkItemType,Title,State,CreatedDate,TargetDate,Custom_ReleasePlannedFor,Custom_TypePHX",
        AREA + "," + TAGS + "," + USER + "," + LINKS)
    log("Build Items (Configuration/RICEFW): %d" % len(raw["cfgs"]))
    raw["cfgsCancelled"] = ado.odata(
        "(WorkItemType eq 'Configuration' or WorkItemType eq 'RICEFW') and "
        "Custom_ReleasePlannedFor eq 'Release 6' and State eq 'Cancelled'",
        "WorkItemId,WorkItemType,State", LINKS)

    raw["pbis"] = ado.odata(
        "WorkItemType eq 'PBI' and " + R6,
        "WorkItemId,Title,State,CreatedDate,TargetDate,Custom_ReleasePlannedFor,Custom_CapabilityGroup,"
        "Custom_Type,Custom_SubTypePHX,Custom_ResponsibleParty",
        AREA + ",Iteration($select=IterationPath)," + USER)
    log("PBIs: %d" % len(raw["pbis"]))

    raw["wss"] = ado.odata(
        "WorkItemType eq 'Activity' and " + R6,
        "WorkItemId,Title,State,CreatedDate,TargetDate,Custom_ReleasePlannedFor,Custom_ComplexTopic",
        AREA + "," + TAGS + "," + USER + "," + LINKS)
    log("Workshops: %d" % len(raw["wss"]))

    raw["raids"] = ado.odata(
        "(WorkItemType eq 'Risk' or WorkItemType eq 'Action' or WorkItemType eq 'Issue' or "
        "WorkItemType eq 'Decision') and " + R6,
        "WorkItemId,WorkItemType,Title,State,CreatedDate,TargetDate,Custom_ReleasePlannedFor,"
        "Custom_CapabilityGroup,Custom_TypePHX,Custom_SubTypePHX,Custom_ImpactTypePHX,Custom_Impact,"
        "Custom_Probability_ACN",
        AREA + "," + TAGS + "," + USER)
    log("RAID items: %d" % len(raw["raids"]))

    raw["eps"] = ado.odata(
        "WorkItemType eq 'Epic' and " + R6,
        "WorkItemId,Title,State,CreatedDate,Custom_ReleasePlannedFor,Custom_CapabilityGroup," + r6f,
        AREA + "," + TAGS + "," + USER + "," + LINKS)
    log("Epics: %d" % len(raw["eps"]))

    raw["kdds"] = ado.odata(
        "WorkItemType eq 'KDD' and " + R6,
        "WorkItemId,WorkItemType,Title,State,CreatedDate,TargetDate,Custom_ReleasePlannedFor",
        AREA + "," + TAGS + "," + USER + "," + LINKS)
    log("KDDs: %d" % len(raw["kdds"]))

    raw["bphs"] = ado.odata(
        "WorkItemType eq 'BPH' and State ne 'Cancelled'",
        "WorkItemId,Title,State,CreatedDate,Custom_ReleasePlannedFor,Custom_CapabilityGroup," + r6f + "," + lvf,
        TAGS + "," + USER + "," + LINKS)
    log("BPHs: %d" % len(raw["bphs"]))
    return raw


# ----------------------------------------------------------------- helpers
def g(x, key):
    v = x.get(key)
    return v


def area_of(x):
    return (x.get("Area") or {}).get("AreaPath") or ""


def tags_of(x):
    return "; ".join(t.get("TagName", "") for t in (x.get("Tags") or []))


def user_of(x):
    return (x.get("AssignedTo") or {}).get("UserName")


def date_only(v):
    if not v:
        return None
    return datetime.datetime.strptime(str(v)[0:10], "%Y-%m-%d")


def plain_text(v):
    if not v:
        return ""
    t = str(v)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</(p|div|li|tr|h[1-6])\s*>", "\n", t)
    t = re.sub(r"(?i)<li(\s[^>]*)?>", "- ", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t).replace("\xa0", " ")
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t[0:32000]


def norm_area(p):
    p = p or ""
    if not p.strip():
        return ""
    if p.startswith("GFPhoenix\\D2D\\D2D - R3") or p.startswith("GFPhoenix\\S2P\\S2P - W1R4"):
        return "Other"
    if p.startswith("GFPhoenix\\Tech Arch"):
        return "Technical"
    if p.startswith("GFPhoenix\\Data"):
        return "MDG" if re.search("MDG|Master Data", p) else "Data Migration"
    if p.startswith("GFPhoenix\\O2C"):
        return "O2C"
    if p.startswith("GFPhoenix\\R2R"):
        return "R2R"
    if p.startswith("GFPhoenix\\S2P") or p.startswith("GFPhoenix\\D2D"):
        return "SCM"
    if p.startswith("GFPhoenix\\M2O"):
        return "M2O"
    if p.startswith("GFPhoenix\\Analytics"):
        return "Analytics"
    return "Other"


def num_of(title):
    m = re.match(r"^\s*(\d+(?:\.\s*\d+)*)", title or "")
    return re.sub(r"\s", "", m.group(1)) if m else None


def first4(num):
    return ".".join(num.split(".")[0:4])


def num_key(num):
    if not num:
        return (999999,)
    return tuple(int(p) for p in num.split(".") if p.isdigit())


# ----------------------------------------------------------------- row builders
def req_row(x, ac):
    a = area_of(x)
    return {
        "Requirement ID": g(x, "WorkItemId"), "Requirement Title": g(x, "Title"),
        "Requirement State": g(x, "State"), "Requirement Assigned To": user_of(x),
        "Requirement Created Date": date_only(g(x, "CreatedDate")),
        "Requirement Target Date": date_only(g(x, "TargetDate")),
        "Requirement Capability Group": g(x, "Custom_CapabilityGroup"),
        "Requirement Complexity": g(x, "Custom_Complexity"),
        "Requirement Complex Topic": g(x, "Custom_ComplexTopic"),
        "Requirement Release Planned for": g(x, "Custom_ReleasePlannedFor"),
        "Requirement Solution Disposition PHX": g(x, "Custom_SolutionDispositionPHX"),
        "Requirement Acceptance Criteria": plain_text(ac.get(str(g(x, "WorkItemId")))),
        "Requirement Area Path": a, "Requirement Normalized Area Path": norm_area(a),
    }


def cfg_row(x):
    a = area_of(x)
    norm = "Data Migration" if g(x, "Custom_TypePHX") == "Conversion" else norm_area(a)
    return {
        "Config ID": g(x, "WorkItemId"), "Config Title": g(x, "Title"), "Config Type": g(x, "WorkItemType"),
        "Config State": g(x, "State"), "Config Assigned To": user_of(x),
        "Config Created Date": date_only(g(x, "CreatedDate")), "Config Target Date": date_only(g(x, "TargetDate")),
        "Config Release Planned for": g(x, "Custom_ReleasePlannedFor"), "Config Type PHX": g(x, "Custom_TypePHX"),
        "Config Area Path": a, "Config Normalized Area Path": norm, "Config Tags": tags_of(x),
    }


def pbi_row(x):
    a = area_of(x)
    return {
        "PBI ID": g(x, "WorkItemId"), "PBI Title": g(x, "Title"), "PBI State": g(x, "State"),
        "PBI Created Date": date_only(g(x, "CreatedDate")), "PBI Target Close": date_only(g(x, "TargetDate")),
        "PBI Capability Group": g(x, "Custom_CapabilityGroup"),
        "PBI Release Planned for": g(x, "Custom_ReleasePlannedFor"), "PBI Type": g(x, "Custom_Type"),
        "PBI Sub Type PHX": g(x, "Custom_SubTypePHX"), "PBI Responsible Party": g(x, "Custom_ResponsibleParty"),
        "PBI Area Path": a, "PBI Normalized Area Path": norm_area(a),
        "PBI Iteration": (x.get("Iteration") or {}).get("IterationPath"), "PBI Assigned To": user_of(x),
    }


def ws_row(x):
    a = area_of(x)
    return {
        "Workshop ID": g(x, "WorkItemId"), "Workshop Title": g(x, "Title"), "Workshop State": g(x, "State"),
        "Workshop Created Date": date_only(g(x, "CreatedDate")),
        "Workshop Target Date": date_only(g(x, "TargetDate")), "Workshop Assigned To": user_of(x),
        "Workshop Release Planned for": g(x, "Custom_ReleasePlannedFor"),
        "Workshop Complex Topic": g(x, "Custom_ComplexTopic"),
        "Workshop Area Path": a, "Workshop Normalized Area Path": norm_area(a), "Workshop Tags": tags_of(x),
    }


def raid_row(x):
    a = area_of(x)
    return {
        "RAID ID": g(x, "WorkItemId"), "RAID Type": g(x, "WorkItemType"), "RAID Title": g(x, "Title"),
        "RAID State": g(x, "State"), "RAID Created Date": date_only(g(x, "CreatedDate")),
        "RAID Target Date": date_only(g(x, "TargetDate")),
        "RAID Area Path": a, "RAID Normalized Area Path": norm_area(a), "RAID Tags": tags_of(x),
        "RAID Release Planned for": g(x, "Custom_ReleasePlannedFor"),
        "RAID Capability Group": g(x, "Custom_CapabilityGroup"), "RAID Type PHX": g(x, "Custom_TypePHX"),
        "RAID Sub Type PHX": g(x, "Custom_SubTypePHX"), "RAID Impact Type PHX": g(x, "Custom_ImpactTypePHX"),
        "RAID Impact": g(x, "Custom_Impact"), "RAID Probability_ACN": g(x, "Custom_Probability_ACN"),
    }


def epic_row(x, r6f):
    a = area_of(x)
    return {
        "Epic ID": g(x, "WorkItemId"), "Epic Title": g(x, "Title"), "Epic State": g(x, "State"),
        "Epic Assigned To": user_of(x), "Epic Created Date": date_only(g(x, "CreatedDate")),
        "Epic Area Path": a, "Epic Normalized Area Path": norm_area(a), "Epic Tags": tags_of(x),
        "Epic Capability Group": g(x, "Custom_CapabilityGroup"),
        "Epic Release Planned for": g(x, "Custom_ReleasePlannedFor"), "Epic R6 Aligned": g(x, r6f),
    }


def kdd_row(x):
    a = area_of(x)
    return {
        "KDD ID": g(x, "WorkItemId"), "KDD Title": g(x, "Title"), "KDD State": g(x, "State"),
        "KDD Assigned To": user_of(x), "KDD Created Date": date_only(g(x, "CreatedDate")),
        "KDD Target Date": date_only(g(x, "TargetDate")),
        "KDD Release Planned for": g(x, "Custom_ReleasePlannedFor"),
        "KDD Area Path": a, "KDD Normalized Area Path": norm_area(a), "KDD Tags": tags_of(x),
    }


# ----------------------------------------------------------------- links
INVERSE = {"Parent": "Child", "Child": "Parent", "Predecessor": "Successor", "Successor": "Predecessor"}


class LinkIndex(object):
    def __init__(self):
        self.name = {}
        self.adj = {}

    def add(self, items):
        for x in items:
            s = str(x.get("WorkItemId"))
            for l in (x.get("Links") or ()):
                t = l.get("TargetWorkItem")
                if not t or t.get("State") == "Cancelled":
                    continue
                tid = str(t.get("WorkItemId"))
                self.name.setdefault((s, tid), l.get("LinkTypeName") or "")
                self.adj.setdefault(s, set()).add(tid)
                self.adj.setdefault(tid, set()).add(s)

    def neighbours(self, wid):
        return self.adj.get(str(wid), set())

    def link_type(self, a, b):
        a, b = str(a), str(b)
        if (a, b) in self.name:
            return self.name.get((a, b))
        n = self.name.get((b, a), "")
        return INVERSE.get(n, n)


def mapping(left_rows, left_id, right_by_id, right_cols, flag, links):
    out = []
    for left in left_rows:
        lid = left.get(left_id)
        targets = sorted((t for t in links.neighbours(lid) if t in right_by_id), key=int)
        if not targets:
            row = dict(left)
            row[flag] = "No"
            row["Link Type"] = None
            for c in right_cols:
                row[c] = None
            out.append(row)
            continue
        for t in targets:
            row = dict(left)
            row[flag] = "Yes"
            row["Link Type"] = links.link_type(lid, t)
            right = right_by_id.get(t)
            for c in right_cols:
                row[c] = right.get(c)
            out.append(row)
    return out


def flag_rows(rows, id_col, flags, links):
    for r in rows:
        nb = links.neighbours(r.get(id_col))
        for name, ids in flags:
            r[name] = "Yes" if any(n in ids for n in nb) else "No"
    return rows


# ----------------------------------------------------------------- BPH hierarchy
def bph_rows(raw, epics):
    lvf = raw["levelField"]
    bph = dict((str(b.get("WorkItemId")), b) for b in raw["bphs"])
    parent, children = {}, {}
    all_bph = raw.get("bphs", [])
    for b in all_bph:
        p = str(b.get("WorkItemId"))
        for l in (b.get("Links") or ()):
            t = l.get("TargetWorkItem") or {}
            c = str(t.get("WorkItemId"))
            if l.get("LinkTypeName") == "Child" and t.get("WorkItemType") == "BPH" and c in bph:
                parent[c] = p
                children.setdefault(p, []).append(c)

    def path(i):
        p, guard = [i], 0
        while i in parent and guard < 10:
            i = parent.get(i)
            p.insert(0, i)
            guard += 1
        return p

    epics_by_num = {}
    for e in epics:
        n = num_of(e.get("Epic Title"))
        if n:
            epics_by_num.setdefault(first4(n), []).append(e)

    l3_epics, matched = {}, set()
    for i in bph:
        pth = path(i)
        if len(pth) == 4:
            n = num_of(bph.get(i).get("Title"))
            for e in epics_by_num.get(n, []):
                l3_epics.setdefault(pth[2], []).append(e)
                matched.add(e.get("Epic ID"))

    def level_cols(pth):
        o = {}
        for k in range(3):
            lv = k + 1
            b = bph.get(pth[k]) if k < len(pth) else None
            o["L%d Number" % lv] = num_of(b.get("Title")) if b else None
            o["L%d BPH ID" % lv] = int(pth[k]) if b else None
            o["L%d Title" % lv] = b.get("Title") if b else None
            o["L%d BPH Level PHX" % lv] = b.get(lvf) if b else None
            o["L%d Capability Group" % lv] = b.get("Custom_CapabilityGroup") if b else None
        return o

    epic_cols = list(epic_row({}, raw["r6Field"]).keys())
    rows = []
    for i in bph:
        pth = path(i)
        depth = len(pth)
        is_leaf_above_l3 = depth < 3 and not children.get(i)
        if depth != 3 and not is_leaf_above_l3:
            continue
        base = level_cols(pth)
        sort_key = tuple(num_key(num_of(bph.get(p).get("Title"))) for p in pth)
        found = []
        seen = set()
        for e in l3_epics.get(i, []):
            if e.get("Epic ID") not in seen:
                seen.add(e.get("Epic ID"))
                found.append(e)
        if found:
            for e in sorted(found, key=lambda z: num_key(num_of(z.get("Epic Title")))):
                r = dict(base)
                r["Match Status"] = "Matched"
                r["Linked to Epic"] = "Yes"
                r.update(e)
                rows.append((sort_key, r))
        else:
            r = dict(base)
            r["Match Status"] = "BPH only" if depth == 3 and children.get(i) else "N/A - no L4"
            r["Linked to Epic"] = "No"
            for c in epic_cols:
                r[c] = None
            rows.append((sort_key, r))
    rows.sort(key=lambda z: z[0])
    out = [r for k, r in rows]
    blank = level_cols([])
    for e in sorted(epics, key=lambda z: num_key(num_of(z.get("Epic Title")))):
        if e.get("Epic ID") not in matched:
            r = dict(blank)
            r["Match Status"] = "Epic only"
            r["Linked to Epic"] = None
            r.update(e)
            out.append(r)
    return out


# ----------------------------------------------------------------- Excel writer
FLAG_COLORS = {"Yes": ("C6EFCE", "006100"), "No": ("FFC7CE", "9C0006")}
MATCH_COLORS = {"Matched": ("C6EFCE", "006100"), "BPH only": ("FFC7CE", "9C0006"),
                "Epic only": ("DDEBF7", "1F4E79"), "N/A - no L4": ("E7E6E6", "595959")}
ID_COLS = {"Requirement ID", "Config ID", "PBI ID", "Workshop ID", "RAID ID", "Epic ID", "KDD ID",
           "L1 BPH ID", "L2 BPH ID", "L3 BPH ID"}


def solid(hex_color):
    return PatternFill(fill_type="solid", start_color=hex_color, end_color=hex_color)


def paint_header(cell, hex_color):
    cell.fill = solid(hex_color)
    cell.font = Font(bold=True, color="FFFFFF")


def table_name(title):
    """Excel table names: letters, digits and underscores only, unique per workbook."""
    return "tbl_" + re.sub(r"\W", "_", title)


def write_sheet(wb, title, rows):
    ws = wb.create_sheet(title)
    if not rows:
        ws.append(["No records found"])
        return
    cols = list(rows[0].keys())
    ws.append(cols)
    for r in rows:
        ws.append([r.get(c) for c in cols])
    last = len(rows) + 1
    for ci, name in enumerate(cols, start=1):
        letter = get_column_letter(ci)
        head = ws.cell(row=1, column=ci)
        head.font = Font(bold=True, color="FFFFFF")  # sits on the table style's coloured header band
        ws.column_dimensions[letter].width = 24
        colours = None
        if name == "Match Status":
            paint_header(head, "C55A11")
            colours = MATCH_COLORS
        elif name.startswith("Linked to "):
            paint_header(head, "2F5597")
            colours = FLAG_COLORS
        is_date = name.endswith(" Date") or name == "PBI Target Close"
        is_id = name in ID_COLS
        is_ac = name == "Requirement Acceptance Criteria"
        if is_ac:
            ws.column_dimensions[letter].width = 60
        if not (colours or is_date or is_id or is_ac):
            continue
        for ri in range(2, last + 1):
            cell = ws.cell(row=ri, column=ci)
            v = cell.value
            if v is None:
                continue
            if colours:
                pair = colours.get(v)
                if pair:
                    cell.fill = solid(pair[0])
                    cell.font = Font(color=pair[1])
            elif is_date:
                cell.number_format = "mm/dd/yyyy"
            elif is_id:
                cell.hyperlink = WI_URL + str(v)
                cell.font = Font(color="0000FF", underline="single")
            elif is_ac:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    # A real Excel table (the filter buttons come with it; a sheet auto_filter on top would corrupt the file).
    tbl = Table(displayName=table_name(title), ref="A1:%s%d" % (get_column_letter(len(cols)), last))
    tbl.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(tbl)


def _primary_id(cols):
    for c in cols:
        if c.endswith(" ID"):
            return c
    return None


def _area_col(cols):
    for c in cols:
        if c.endswith("Normalized Area Path"):
            return c
    return None


def summary_lines(title, rows):
    out = [("H", title, None)]
    if not rows:
        out.append(("M", "No records found", 0))
        return out
    cols = list(rows[0].keys())
    if "Match Status" in cols:
        out.append(("T", "Total rows", len(rows)))
        for st in ("Matched", "BPH only", "Epic only", "N/A - no L4"):
            out.append(("M", "    " + st, sum(1 for r in rows if r.get("Match Status") == st)))
        out.append(("M", "    Distinct L3 BPHs", len(set(r.get("L3 BPH ID") for r in rows if r.get("L3 BPH ID")))))
        out.append(("M", "    Distinct Epics matched", len(set(r.get("Epic ID") for r in rows if r.get("Match Status") == "Matched"))))
        return out
    pid = _primary_id(cols)
    noun = pid.replace(" ID", "") if pid else "Item"
    noun = "Build Item" if noun == "Config" else noun
    ids = set(r.get(pid) for r in rows if r.get(pid) is not None)
    out.append(("T", "Total %ss" % noun, len(ids)))
    flags = list(c for c in cols if c.startswith("Linked to ") and not (title == "RAID_Items" and c == "Linked to KDD"))
    for fl in flags:
        target = fl.replace("Linked to ", "")
        yes_ids = set(r.get(pid) for r in rows if r.get(fl) == "Yes")
        out.append(("M", "    Linked to %s" % target, len(yes_ids)))
        out.append(("M", "    Not linked to %s" % target, len(ids - yes_ids)))
        if len(rows) != len(ids):
            out.append(("M", "    Total %s links" % target, sum(1 for r in rows if r.get(fl) == "Yes")))
    ac = _area_col(cols)
    if ac:
        by = {}
        for r in rows:
            by.setdefault(r.get(ac) or "No area path", set()).add(r.get(pid))
        for a in sorted(by):
            out.append(("A", "    Area: %s" % a, len(by.get(a))))
    return out


def write_summary(wb, title, sheets):
    ws = wb.create_sheet("Summary", 0)
    ws.sheet_view.showGridLines = False
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=16, color="1F3864")
    ws["A2"] = "Last refreshed: " + datetime.datetime.now().strftime("%m/%d/%Y %H:%M")
    ws["A2"].font = Font(italic=True, color="595959")
    palette = [("1F4E79", "DDEBF7"), ("375623", "E2EFDA"), ("C55A11", "FCE4D6"),
               ("7030A0", "E4DFEC"), ("00737A", "D5F0F1"), ("44546A", "D6DCE4")]
    r = 4
    for n, item in enumerate(sheets):
        sheet, rows = item
        dark, light = palette[n % len(palette)]
        for kind, label, value in summary_lines(sheet, rows):
            a, b, c = ws.cell(r, 1), ws.cell(r, 2), ws.cell(r, 3)
            if kind == "H":
                for cell in (a, b, c):
                    cell.fill = solid(dark)
                    cell.font = Font(bold=True, color="FFFFFF")
                a.value, b.value, c.value = sheet.replace("_", " ").upper(), "Count", "Go to"
            else:
                for cell in (a, b, c):
                    cell.fill = solid(light)
                a.value, b.value = label, value
                b.font = Font(bold=True, color=dark)
                c.value = "=HYPERLINK(\"#'" + sheet + "'!A1\",\"Open >\")"
                c.font = Font(underline="single", color=dark)
                if kind == "T":
                    a.font = Font(bold=True)
            b.alignment = Alignment(horizontal="center")
            c.alignment = Alignment(horizontal="center")
            r += 1
        r += 1
    ws.column_dimensions["A"].width = 60
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 12
    ws.freeze_panes = "A4"


def save_workbook(path, sheets):
    wb = Workbook()
    default = wb.active
    for title, rows in sheets:
        write_sheet(wb, title, rows)
        log("  %s: %d rows" % (title, len(rows)))
    wb.remove(default)
    name = os.path.splitext(os.path.basename(path))[0]
    name = re.sub(r"_\d{4}-\d{2}-\d{2}_\d{6}$", "", name).replace("_", " ")
    write_summary(wb, "Release 6 Traceability - " + name, sheets)
    wb.active = 0
    wb.save(path)
    log("Saved " + path)

def apply_exclusions(raw):
    """Workshops and PBIs left after the report exclusions, and the link index over everything kept."""
    # Exclusions (same as the PowerShell report)
    wss = [w for w in raw["wss"] if EXCLUDE_WS_TAG not in [t.strip() for t in tags_of(w).split(";")]]
    log("Workshops excluded - Tag %s: %d" % (EXCLUDE_WS_TAG, len(raw["wss"]) - len(wss)))

    links = LinkIndex()
    for key in ("cfgs", "cfgsCancelled", "eps", "kdds"):
        links.add(raw.get(key, []))
    links.add(wss)

    active_cfg = set(str(x.get("WorkItemId")) for x in raw["cfgs"])
    cancelled_cfg = set(str(x.get("WorkItemId")) for x in raw.get("cfgsCancelled", []))
    pbis, excl_area, excl_parent = [], 0, 0
    raw_pbis = raw.get("pbis", [])
    for x in raw_pbis:
        a = area_of(x)
        if a == EXCLUDE_PBI_AREA or a.startswith(EXCLUDE_PBI_AREA + "\\"):
            excl_area += 1
            continue
        nb = links.neighbours(x.get("WorkItemId"))
        if any(n in cancelled_cfg for n in nb) and not any(n in active_cfg for n in nb):
            excl_parent += 1
            continue
        pbis.append(x)
    log("PBIs excluded - parent Build Item Cancelled: %d, Area %s: %d" % (excl_parent, EXCLUDE_PBI_AREA, excl_area))
    return wss, pbis, links


# ----------------------------------------------------------------- main
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-cache", action="store_true", help="rebuild from the data saved by the last run")
    ap.add_argument("--out", default=here, help="parent folder for the new output folder")
    ap.add_argument("--asof", default=None, help="reporting date for the DataSync workbook, YYYY-MM-DD (default today)")
    ap.add_argument("--datasync-only", action="store_true", help="write only Phoenix_R6_DataSync.xlsx, not the 4 reports")
    args = ap.parse_args()
    cache = os.path.join(here, "ado_r6_python_cache.json")

    if args.use_cache:
        with open(cache, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        log("Loaded saved data (no ADO calls)")
    else:
        pat = os.environ.get("ADO_PAT")
        if not pat:
            sys.exit("ADO_PAT is not set.")
        raw = pull_all(Ado(pat))
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(raw, fh)
        log("Data saved for --use-cache reruns")

    wss, pbis, links = apply_exclusions(raw)

    by_id = lambda rows, col: dict((str(r.get(col)), r) for r in rows)
    reqs = sorted((req_row(x, raw.get("ac", {})) for x in raw["reqs"]), key=lambda r: r.get("Requirement ID"))
    cfgs = sorted((cfg_row(x) for x in raw["cfgs"]), key=lambda r: r.get("Config ID"))
    pbi_list = sorted((pbi_row(x) for x in pbis), key=lambda r: r.get("PBI ID"))
    ws_list = sorted((ws_row(x) for x in wss), key=lambda r: r.get("Workshop ID"))
    raids = sorted((raid_row(x) for x in raw["raids"]), key=lambda r: r.get("RAID ID"))
    epics = sorted((epic_row(x, raw["r6Field"]) for x in raw["eps"]), key=lambda r: r.get("Epic ID"))
    kdds = sorted((kdd_row(x) for x in raw["kdds"]), key=lambda r: r.get("KDD ID"))

    req_by, cfg_by, pbi_by = by_id(reqs, "Requirement ID"), by_id(cfgs, "Config ID"), by_id(pbi_list, "PBI ID")
    ws_by, ep_by, kdd_by = by_id(ws_list, "Workshop ID"), by_id(epics, "Epic ID"), by_id(kdds, "KDD ID")
    cols = lambda fn: list(fn({}).keys())
    req_cols = list(req_row({}, {}).keys())
    ep_cols = list(epic_row({}, raw["r6Field"]).keys())

    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder = os.path.join(args.out, "R6_Traceability_Python_" + stamp)
    os.makedirs(folder, exist_ok=True)

    try:
        from .ado_to_datasync import write_datasync_workbook
    except ImportError:  # run as a plain script
        from ado_to_datasync import write_datasync_workbook
    write_datasync_workbook(raw, os.path.join(folder, "Phoenix_R6_DataSync.xlsx"), args.asof)
    if args.datasync_only:
        print("\nDone in %.0f seconds. Files saved in: %s" % (time.time() - START, folder))
        return

    save_workbook(os.path.join(folder, "01_BPH_L1-L3_to_Epic_%s.xlsx" % stamp), [
        ("BPH_L1-L3_to_Epic", bph_rows(raw, epics)),
    ])
    save_workbook(os.path.join(folder, "02_Epic_Mappings_%s.xlsx" % stamp), [
        ("Epic_to_KDD", mapping(epics, "Epic ID", kdd_by, cols(kdd_row), "Linked to KDD", links)),
        ("Epic_to_Requirements", mapping(epics, "Epic ID", req_by, req_cols, "Linked to Requirement", links)),
        ("Epic_to_Workshops", mapping(epics, "Epic ID", ws_by, cols(ws_row), "Linked to Workshop", links)),
        ("Epic_to_Build_Items", mapping(epics, "Epic ID", cfg_by, cols(cfg_row), "Linked to Build Item", links)),
        ("Requirement_to_Workshops", mapping(reqs, "Requirement ID", ws_by, cols(ws_row), "Linked to Workshop", links)),
    ])
    save_workbook(os.path.join(folder, "03_Requirement_BuildItem_PBI_%s.xlsx" % stamp), [
        ("Requirement_to_Build_Items", mapping(reqs, "Requirement ID", cfg_by, cols(cfg_row), "Linked to Build Item", links)),
        ("Build_Item_to_PBI", mapping(cfgs, "Config ID", pbi_by, cols(pbi_row), "Linked to PBI", links)),
    ])
    save_workbook(os.path.join(folder, "04_RAID_Items_%s.xlsx" % stamp), [
        ("RAID_Items", flag_rows(raids, "RAID ID",
                                 [("Linked to Workshop", ws_by), ("Linked to Epic", ep_by)],
                                 links)),
    ])
    print("\nDone in %.0f seconds. Files saved in: %s" % (time.time() - START, folder))


if __name__ == "__main__":
    main()
