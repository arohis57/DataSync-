"""
Phoenix R6 master program  -  ONE file that produces everything.

Each run pulls Azure DevOps once and creates, in one new dated folder:
  01_BPH_L1-L3_to_Epic_<stamp>.xlsx
  02_Epic_Mappings_<stamp>.xlsx
  03_Requirement_BuildItem_PBI_<stamp>.xlsx
  04_RAID_Items_<stamp>.xlsx
  Phoenix_R6_DataSync.xlsx            (Excel tables read by the DataSync job, see docs/data_model.md)
  Phoenix R6 Program Cockpit_<stamp>.html
and then checks the cockpit against cockpit_template.html.

  python phoenix_r6_master.py                 full run (pulls ADO)
  python phoenix_r6_master.py --use-cache     rebuild from the data saved by the last run
  python phoenix_r6_master.py --publish "C:\\...\\R6 Traceability Reports"

Change the folder paths in the SETTINGS block below (or pass --out / --publish).
Needs the ADO_PAT environment variable, and cockpit_template.html next to this file.
The DataSync workbook uses the repo's datasync package: pip install -e ".[ado]" first.
"""
import argparse
import base64
import datetime
import glob
import html
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import quote

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import requests
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

try:
    from .workbook_writer import write_workbook
except ImportError:  # run as a plain script
    from datasync.workbook_writer import write_workbook

HERE = os.path.dirname(os.path.abspath(__file__))

# =============================== SETTINGS ===============================
# Every run creates a new dated folder inside OUTPUT_ROOT.
OUTPUT_ROOT = os.path.join(HERE, "Reports")
# Optional: a synced SharePoint folder. Leave "" to skip publishing.
PUBLISH_FOLDER = ""
# The locked cockpit template (never edit it by hand).
TEMPLATE = os.path.join(HERE, "cockpit_template.html")
# Saved ADO data used by --use-cache (kept out of the output folder on purpose).
DATA_DIR = os.path.join(HERE, "_data")
ORG_PROJECT = "Program-Phoenix/GFPhoenix"
RELEASE = "Release 6"
EXCLUDE_WS_TAG = "Signavio Process Flow"
EXCLUDE_PBI_AREA = "GFPhoenix\\Change_OCM"
# Fixed name (no stamp): the Power Automate flow fetches it by path.
DATASYNC_FILE = "Phoenix_R6_DataSync.xlsx"
# ========================================================================

ANALYTICS = "https://analytics.dev.azure.com/" + ORG_PROJECT + "/_odata/v4.0-preview/WorkItems"
WI_URL = "https://dev.azure.com/" + ORG_PROJECT + "/_workitems/edit/"
REST_WI = "https://dev.azure.com/" + ORG_PROJECT + "/_apis/wit/workitems"
R6 = "Custom_ReleasePlannedFor eq '" + RELEASE + "' and State ne 'Cancelled'"
LINKS = "Links($select=LinkTypeName;$expand=TargetWorkItem($select=WorkItemId,WorkItemType,Title,State))"
AREA = "Area($select=AreaPath)"
TAGS = "Tags($select=TagName)"
USER = "AssignedTo($select=UserName,UserEmail)"
AC_FIELD = "Microsoft.VSTS.Common.AcceptanceCriteria"
RAID_TYPES = ("Risk", "Action", "Issue", "Decision")
RAID_LETTER = {"Action": "A", "Risk": "R", "Issue": "I", "Decision": "D"}
DONE_PBI = ("Completed", "Ready for Acceptance")
CACHE_VERSION = 3

START = time.time()


def log(msg):
    print("  [%4.0fs] %s" % (time.time() - START, msg), flush=True)


# ----- ADO ACCESS
class AdoClientError(Exception):
    pass


class Ado(object):
    def __init__(self, pat):
        token = base64.b64encode((":" + pat).encode("ascii")).decode("ascii")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": "Basic " + token})

    def get(self, url, tries=5):
        for attempt in range(1, tries + 1):
            try:
                r = self.s.get(url, timeout=300)
                if 400 <= r.status_code < 500 and r.status_code != 429:
                    raise AdoClientError("HTTP %d: %s" % (r.status_code, r.text[0:300]))
                r.raise_for_status()
                return r
            except AdoClientError:
                raise
            except Exception as e:
                print("  Attempt %d failed: %s" % (attempt, e), flush=True)
                if attempt == tries:
                    raise
                time.sleep(30 * attempt)

    def odata(self, flt, select, expand=None, tries=5):
        url = ANALYTICS + "?$filter=" + quote(flt, safe="") + "&$select=" + select
        if expand:
            url = url + "&$expand=" + expand
        rows = []
        while url:
            data = self.get(url, tries).json()
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


def discover(meta, patterns, label, required=False):
    names = sorted(set(re.findall(r'Name="([^"]+)"', meta)))
    for pat in patterns:
        hits = list(n for n in names if re.search(pat, n))
        if hits:
            log("%s field: %s" % (label, hits[0]))
            return hits[0]
    if required:
        raise RuntimeError(label + " field not found in Analytics metadata.")
    log("%s field: not found - column left blank" % label)
    return None


def pull_all(ado):
    """One pull that serves the Excel files and the cockpit."""
    raw = {"version": CACHE_VERSION}
    meta = ado.get(ANALYTICS.replace("/WorkItems", "") + "/$metadata").text
    raw["r6Field"] = discover(meta, [r"R6.*Align|Align.*R6"], "R6 Aligned", True)
    raw["levelField"] = discover(meta, [r"BPH.*Level|Level.*PHX"], "BPH Level PHX", True)
    raw["kddType"] = discover(meta, [r"^Custom_TypePHX$", r"^Custom_\w*KDD\w*Type"], "KDD type")
    raw["kddDecided"] = discover(meta, [r"^Custom_ApprovedDate$", r"^Custom_\w*(Decision|Approv)\w*Date"],
                                 "KDD decision date")
    r6f, lvf = raw["r6Field"], raw["levelField"]
    q = ado.odata

    raw["reqs"] = q("WorkItemType eq 'Requirement' and " + R6,
                    "WorkItemId,Title,State,CreatedDate,TargetDate,Custom_ReleasePlannedFor,Custom_CapabilityGroup,"
                    "Custom_ComplexTopic,Custom_Complexity,Custom_SolutionDispositionPHX", AREA + "," + USER)
    log("Requirements: %d" % len(raw["reqs"]))
    raw["ac"] = ado.acceptance_criteria([x["WorkItemId"] for x in raw["reqs"]])
    log("Acceptance Criteria pulled")

    cfg_sel = "WorkItemId,WorkItemType,Title,State,CreatedDate,TargetDate,Custom_ReleasePlannedFor,Custom_TypePHX"
    cfg_type = "(WorkItemType eq 'Configuration' or WorkItemType eq 'RICEFW') and "
    raw["cfgs"] = q(cfg_type + R6, cfg_sel, AREA + "," + TAGS + "," + USER + "," + LINKS)
    log("Build Items (Configuration/RICEFW): %d" % len(raw["cfgs"]))
    raw["cfgsCancelled"] = q(cfg_type + "Custom_ReleasePlannedFor eq '" + RELEASE + "' and State eq 'Cancelled'",
                             "WorkItemId,WorkItemType,State", LINKS)

    raw["pbis"] = q("WorkItemType eq 'PBI' and " + R6,
                    "WorkItemId,Title,State,CreatedDate,TargetDate,Custom_ReleasePlannedFor,Custom_CapabilityGroup,"
                    "Custom_Type,Custom_SubTypePHX,Custom_ResponsibleParty",
                    AREA + ",Iteration($select=IterationPath)," + USER)
    log("PBIs: %d" % len(raw["pbis"]))

    ws_sel = "WorkItemId,Title,State,CreatedDate,TargetDate,Custom_ReleasePlannedFor,Custom_ComplexTopic"
    ws_exp = AREA + "," + TAGS + "," + USER + "," + LINKS
    raw["wssFiltered"] = False
    try:
        flt = "WorkItemType eq 'Activity' and not Tags/any(t:t/TagName eq '" + EXCLUDE_WS_TAG + "') and " + R6
        raw["wss"] = q(flt, ws_sel, ws_exp, tries=2)
        raw["wssFiltered"] = True
    except Exception as e:
        print("  Tag filter not accepted by ADO (%s) - pulling all workshops and excluding them here." % str(e)[0:120])
        raw["wss"] = q("WorkItemType eq 'Activity' and " + R6, ws_sel, ws_exp)
    log("Workshops: %d" % len(raw["wss"]))

    raw["raids"] = q("(WorkItemType eq 'Risk' or WorkItemType eq 'Action' or WorkItemType eq 'Issue' or "
                     "WorkItemType eq 'Decision') and " + R6,
                     "WorkItemId,WorkItemType,Title,State,CreatedDate,TargetDate,Custom_ReleasePlannedFor,"
                     "Custom_CapabilityGroup,Custom_TypePHX,Custom_SubTypePHX,Custom_ImpactTypePHX,Custom_Impact,"
                     "Custom_Probability_ACN", AREA + "," + TAGS + "," + USER)
    log("RAID items: %d" % len(raw["raids"]))

    raw["eps"] = q("WorkItemType eq 'Epic' and " + R6,
                   "WorkItemId,Title,State,CreatedDate,Custom_ReleasePlannedFor,Custom_CapabilityGroup," + r6f,
                   AREA + "," + TAGS + "," + USER + "," + LINKS)
    log("Epics: %d" % len(raw["eps"]))

    ksel = "WorkItemId,WorkItemType,Title,State,CreatedDate,TargetDate,StateChangeDate,Custom_ReleasePlannedFor"
    for extra in (raw["kddType"], raw["kddDecided"]):
        if extra:
            ksel = ksel + "," + extra
    raw["kdds"] = q("WorkItemType eq 'KDD' and " + R6, ksel, AREA + "," + TAGS + "," + USER + "," + LINKS)
    log("KDDs: %d" % len(raw["kdds"]))

    raw["bphs"] = q("WorkItemType eq 'BPH' and State ne 'Cancelled'",
                    "WorkItemId,Title,State,CreatedDate,Custom_ReleasePlannedFor,Custom_CapabilityGroup,"
                    + r6f + "," + lvf, TAGS + "," + USER + "," + LINKS)
    log("BPHs: %d" % len(raw["bphs"]))
    return raw


# ----- HELPERS
def sid(x):
    return str(x.get("WorkItemId"))


def area_of(x):
    return (x.get("Area") or {}).get("AreaPath") or ""


def tags_of(x):
    return "; ".join(t.get("TagName", "") for t in (x.get("Tags") or ()))


def user_of(x):
    return (x.get("AssignedTo") or {}).get("UserName")


def day(v):
    return str(v)[0:10] if v else None


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
    return re.sub(r"\s", "", m.group(1)) if m else ""


def first4(num):
    return ".".join(num.split(".")[0:4])


def strip_num(title):
    return re.sub(r"^\s*\d+(?:\.\s*\d+)*\s*[-:.]?\s*", "", title or "").strip()


def num_key(n):
    return tuple(int(p) for p in n.split(".") if p.isdigit()) if n else (999999,)


INVERSE = {"Parent": "Child", "Child": "Parent", "Predecessor": "Successor", "Successor": "Predecessor"}


class LinkIndex(object):
    """Who is linked to whom, built once and used by both the Excel files and the cockpit."""

    def __init__(self):
        self.name = {}
        self.adj = {}
        self.typ = {}

    def add(self, items, typ=None):
        for x in items:
            s = sid(x)
            if typ is not None:
                self.typ[s] = typ(x) if callable(typ) else typ
            for l in (x.get("Links") or ()):
                t = l.get("TargetWorkItem")
                if not t or t.get("State") == "Cancelled":
                    continue
                tid = str(t.get("WorkItemId"))
                self.typ.setdefault(tid, t.get("WorkItemType"))
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


def prepare(raw):
    """Applies the exclusions and builds the shared link index."""
    wss = [w for w in raw["wss"] if EXCLUDE_WS_TAG not in [t.strip() for t in tags_of(w).split(";")]]
    if raw.get("wssFiltered"):
        log("Workshops: %d (tag %s is excluded in the ADO query)" % (len(wss), EXCLUDE_WS_TAG))
    else:
        log("Workshops excluded - Tag %s: %d" % (EXCLUDE_WS_TAG, len(raw["wss"]) - len(wss)))
    links = LinkIndex()
    links.add(raw["eps"], "Epic")
    links.add(wss, "Activity")
    links.add(raw["kdds"], "KDD")
    links.add(raw["reqs"], "Requirement")
    links.add(raw["cfgs"], lambda x: x.get("WorkItemType"))
    links.add(raw["cfgsCancelled"], lambda x: x.get("WorkItemType"))
    links.add(raw["pbis"], "PBI")

    active_cfg = set(sid(x) for x in raw["cfgs"])
    cancelled_cfg = set(sid(x) for x in raw["cfgsCancelled"])
    pbis, excluded = [], []
    all_pbis = list(raw["pbis"])
    for x in all_pbis:
        nb = links.neighbours(sid(x))
        cancelled_parents = sorted((n for n in nb if n in cancelled_cfg), key=int)
        active_parents = sorted((n for n in nb if n in active_cfg), key=int)
        if EXCLUDE_PBI_AREA.lower() in area_of(x).lower():
            reason = "Area Path contains " + EXCLUDE_PBI_AREA
        elif cancelled_parents and not active_parents:
            reason = "All linked RICEFW/Configuration parents are Cancelled"
        else:
            pbis.append(x)
            continue
        excluded.append((x, reason, cancelled_parents, active_parents))
    log("PBIs excluded: %d (of %d)" % (len(excluded), len(raw["pbis"])))
    return {"raw": raw, "wss": wss, "links": links, "pbis": pbis, "pbis_excluded": excluded}

# ----- EXCEL: ROW BUILDERS
def release_of(x):
    """Release Planned For. Every query filters on it, so a blank means ADO did not return the field."""
    return x.get("Custom_ReleasePlannedFor") or RELEASE


def req_row(x, ac):
    a = area_of(x)
    return {
        "Requirement ID": x.get("WorkItemId"), "Requirement Title": x.get("Title"),
        "Requirement State": x.get("State"), "Requirement Assigned To": user_of(x),
        "Requirement Created Date": date_only(x.get("CreatedDate")),
        "Requirement Target Date": date_only(x.get("TargetDate")),
        "Requirement Capability Group": x.get("Custom_CapabilityGroup"),
        "Requirement Complexity": x.get("Custom_Complexity"),
        "Requirement Complex Topic": x.get("Custom_ComplexTopic"),
        "Requirement Release Planned for": release_of(x),
        "Requirement Solution Disposition PHX": x.get("Custom_SolutionDispositionPHX"),
        "Requirement Acceptance Criteria": plain_text(ac.get(sid(x))),
        "Requirement Area Path": a, "Requirement Normalized Area Path": norm_area(a),
    }


def cfg_row(x):
    a = area_of(x)
    norm = "Data Migration" if x.get("Custom_TypePHX") == "Conversion" else norm_area(a)
    return {
        "Config ID": x.get("WorkItemId"), "Config Title": x.get("Title"), "Config Type": x.get("WorkItemType"),
        "Config State": x.get("State"), "Config Assigned To": user_of(x),
        "Config Created Date": date_only(x.get("CreatedDate")), "Config Target Date": date_only(x.get("TargetDate")),
        "Config Release Planned for": release_of(x), "Config Type PHX": x.get("Custom_TypePHX"),
        "Config Area Path": a, "Config Normalized Area Path": norm, "Config Tags": tags_of(x),
    }


def pbi_row(x):
    a = area_of(x)
    return {
        "PBI ID": x.get("WorkItemId"), "PBI Title": x.get("Title"), "PBI State": x.get("State"),
        "PBI Created Date": date_only(x.get("CreatedDate")), "PBI Target Close": date_only(x.get("TargetDate")),
        "PBI Capability Group": x.get("Custom_CapabilityGroup"),
        "PBI Release Planned for": release_of(x), "PBI Type": x.get("Custom_Type"),
        "PBI Sub Type PHX": x.get("Custom_SubTypePHX"), "PBI Responsible Party": x.get("Custom_ResponsibleParty"),
        "PBI Area Path": a, "PBI Normalized Area Path": norm_area(a),
        "PBI Iteration": (x.get("Iteration") or {}).get("IterationPath"), "PBI Assigned To": user_of(x),
    }


def ws_row(x):
    a = area_of(x)
    return {
        "Workshop ID": x.get("WorkItemId"), "Workshop Title": x.get("Title"), "Workshop State": x.get("State"),
        "Workshop Created Date": date_only(x.get("CreatedDate")),
        "Workshop Target Date": date_only(x.get("TargetDate")), "Workshop Assigned To": user_of(x),
        "Workshop Release Planned for": release_of(x),
        "Workshop Complex Topic": x.get("Custom_ComplexTopic"),
        "Workshop Area Path": a, "Workshop Normalized Area Path": norm_area(a), "Workshop Tags": tags_of(x),
    }


def raid_row(x):
    a = area_of(x)
    return {
        "RAID ID": x.get("WorkItemId"), "RAID Type": x.get("WorkItemType"), "RAID Title": x.get("Title"),
        "RAID State": x.get("State"), "RAID Created Date": date_only(x.get("CreatedDate")),
        "RAID Target Date": date_only(x.get("TargetDate")),
        "RAID Area Path": a, "RAID Normalized Area Path": norm_area(a), "RAID Tags": tags_of(x),
        "RAID Release Planned for": release_of(x),
        "RAID Capability Group": x.get("Custom_CapabilityGroup"), "RAID Type PHX": x.get("Custom_TypePHX"),
        "RAID Sub Type PHX": x.get("Custom_SubTypePHX"), "RAID Impact Type PHX": x.get("Custom_ImpactTypePHX"),
        "RAID Impact": x.get("Custom_Impact"), "RAID Probability_ACN": x.get("Custom_Probability_ACN"),
    }


def epic_row(x, r6f):
    a = area_of(x)
    return {
        "Epic ID": x.get("WorkItemId"), "Epic Title": x.get("Title"), "Epic State": x.get("State"),
        "Epic Assigned To": user_of(x), "Epic Created Date": date_only(x.get("CreatedDate")),
        "Epic Area Path": a, "Epic Normalized Area Path": norm_area(a), "Epic Tags": tags_of(x),
        "Epic Capability Group": x.get("Custom_CapabilityGroup"),
        "Epic Release Planned for": release_of(x), "Epic R6 Aligned": x.get(r6f),
    }


def kdd_row(x):
    a = area_of(x)
    return {
        "KDD ID": x.get("WorkItemId"), "KDD Title": x.get("Title"), "KDD State": x.get("State"),
        "KDD Assigned To": user_of(x), "KDD Created Date": date_only(x.get("CreatedDate")),
        "KDD Target Date": date_only(x.get("TargetDate")),
        "KDD Release Planned for": release_of(x),
        "KDD Area Path": a, "KDD Normalized Area Path": norm_area(a), "KDD Tags": tags_of(x),
    }


# ----- EXCEL: MAPPINGS
def mapping(left_rows, left_id, right_by_id, right_cols, flag, links, orphans=None):
    """One row per link. Left items with no link get one 'No' row.
    With orphans set, right items that nothing links to are added at the end, so none are lost."""
    out = []
    used = set()
    blank_left = dict((k, None) for k in (left_rows[0].keys() if left_rows else ()))
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
            used.add(t)
            row = dict(left)
            row[flag] = "Yes"
            row["Link Type"] = links.link_type(lid, t)
            right = right_by_id.get(t)
            for c in right_cols:
                row[c] = right.get(c)
            out.append(row)
    if orphans:
        missing = sorted((t for t in right_by_id if t not in used), key=int)
        for t in missing:
            row = dict(blank_left)
            row[flag] = None
            row["Link Type"] = orphans
            right = right_by_id.get(t)
            for c in right_cols:
                row[c] = right.get(c)
            out.append(row)
        noun = right_cols[0].replace(" ID", "") if right_cols else "item"
        log("    %s coverage: all %d included, %d linked, %d with %s" % (noun, len(right_by_id), len(used), len(missing), orphans))
    return out


def flag_rows(rows, id_col, flags, links):
    for r in rows:
        nb = links.neighbours(r.get(id_col))
        for name, ids in flags:
            r[name] = "Yes" if any(n in ids for n in nb) else "No"
    return rows


def bph_rows(raw, epics):
    """BPH L1 -> L2 -> L3 with the Epics matched through the L4 number (L4 itself is not shown)."""
    lvf = raw["levelField"]
    bph = dict((sid(b), b) for b in raw["bphs"])
    parent, children = {}, {}
    all_bph = list(raw["bphs"])
    for b in all_bph:
        p = sid(b)
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
            for e in epics_by_num.get(n, ()):
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
        found, seen = [], set()
        for e in l3_epics.get(i, ()):
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


# ----- EXCEL: WRITER
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


def ordered_excel_columns(columns):
    """Area Path columns first, then Normalized Area Path columns, then everything else."""
    columns = list(columns)
    raw_area = [c for c in columns if c.endswith(" Area Path") and "Normalized Area Path" not in c]
    norm_area_cols = [c for c in columns if c.endswith("Normalized Area Path")]
    rest = [c for c in columns if c not in raw_area and c not in norm_area_cols]
    return raw_area + norm_area_cols + rest


def write_sheet(wb, title, rows):
    ws = wb.create_sheet(title)
    if not rows:
        ws.append(["No records found"])
        return
    cols = ordered_excel_columns(rows[0].keys())
    ws.append(cols)
    for r in rows:
        ws.append([r.get(c) for c in cols])
    last = len(rows) + 1
    for ci, name in enumerate(cols, start=1):
        letter = get_column_letter(ci)
        head = ws.cell(row=1, column=ci)
        head.font = Font(bold=True)
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
    ws.auto_filter.ref = "A1:%s%d" % (get_column_letter(len(cols)), last)


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
    orphan = list(r for r in rows if r.get(pid) is None)
    if orphan:
        oid = next((c for c in cols if c.endswith(" ID") and c != pid and any(r.get(c) is not None for r in orphan)), None)
        if oid:
            out.append(("M", "    %ss with no R6 %s linked" % (oid.replace(" ID", ""), noun), len(set(r.get(oid) for r in orphan))))
    flags = list(c for c in cols if c.startswith("Linked to "))
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
            if r.get(pid) is None:
                continue
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
    write_summary(wb, RELEASE + " Traceability - " + name, sheets)
    wb.active = 0
    wb.save(path)
    log("Saved " + path)


def build_excel(ctx, folder, stamp):
    raw, links = ctx["raw"], ctx["links"]
    blank = sum(1 for x in raw["reqs"] if not x.get("Custom_ReleasePlannedFor"))
    if blank:
        log("Release Planned For came back blank from ADO for %d of %d requirements; showing %s from the query" % (blank, len(raw["reqs"]), RELEASE))
    by_id = lambda rows, col: dict((str(r.get(col)), r) for r in rows)
    reqs = sorted((req_row(x, raw.get("ac", {})) for x in raw["reqs"]), key=lambda r: r.get("Requirement ID"))
    cfgs = sorted((cfg_row(x) for x in raw["cfgs"]), key=lambda r: r.get("Config ID"))
    pbi_list = sorted((pbi_row(x) for x in ctx["pbis"]), key=lambda r: r.get("PBI ID"))
    ws_list = sorted((ws_row(x) for x in ctx["wss"]), key=lambda r: r.get("Workshop ID"))
    raids = sorted((raid_row(x) for x in raw["raids"]), key=lambda r: r.get("RAID ID"))
    epics = sorted((epic_row(x, raw["r6Field"]) for x in raw["eps"]), key=lambda r: r.get("Epic ID"))
    kdds = sorted((kdd_row(x) for x in raw["kdds"]), key=lambda r: r.get("KDD ID"))

    excluded = []
    excluded_src = list(ctx["pbis_excluded"])
    for x, reason, cancelled_parents, active_parents in excluded_src:
        row = pbi_row(x)
        row["Cancelled Parent Build Item IDs"] = "; ".join(cancelled_parents)
        row["Active Parent Build Item IDs"] = "; ".join(active_parents)
        row["Exclusion Reason"] = reason
        excluded.append(row)
    excluded.sort(key=lambda r: r.get("PBI ID"))

    req_by, cfg_by, pbi_by = by_id(reqs, "Requirement ID"), by_id(cfgs, "Config ID"), by_id(pbi_list, "PBI ID")
    ws_by, ep_by, kdd_by = by_id(ws_list, "Workshop ID"), by_id(epics, "Epic ID"), by_id(kdds, "KDD ID")
    cols = lambda fn: list(fn({}).keys())
    req_cols = list(req_row({}, {}).keys())

    def p(n, name):
        return os.path.join(folder, "%s_%s.xlsx" % (n + name, stamp))

    save_workbook(p("01_", "BPH_L1-L3_to_Epic"), [
        ("BPH_L1-L3_to_Epic", bph_rows(raw, epics)),
    ])
    save_workbook(p("02_", "Epic_Mappings"), [
        ("Epic_to_KDD", mapping(epics, "Epic ID", kdd_by, cols(kdd_row), "Linked to KDD", links, orphans="No R6 Epic linked")),
        ("Epic_to_Requirements", mapping(epics, "Epic ID", req_by, req_cols, "Linked to Requirement", links)),
        ("Epic_to_Workshops", mapping(epics, "Epic ID", ws_by, cols(ws_row), "Linked to Workshop", links)),
        ("Epic_to_Build_Items", mapping(epics, "Epic ID", cfg_by, cols(cfg_row), "Linked to Build Item", links)),
        ("Requirement_to_Workshops", mapping(reqs, "Requirement ID", ws_by, cols(ws_row), "Linked to Workshop", links)),
    ])
    save_workbook(p("03_", "Requirement_BuildItem_PBI"), [
        ("Requirement_to_Build_Items", mapping(reqs, "Requirement ID", cfg_by, cols(cfg_row), "Linked to Build Item", links)),
        ("Build_Item_to_PBI", mapping(cfgs, "Config ID", pbi_by, cols(pbi_row), "Linked to PBI", links)),
        ("Excluded_PBIs", excluded),
    ])
    save_workbook(p("04_", "RAID_Items"), [
        ("RAID_Items", flag_rows(raids, "RAID ID", [("Linked to Workshop", ws_by), ("Linked to Epic", ep_by)], links)),
        ("KDD_Items", flag_rows([dict(r) for r in kdds], "KDD ID", [("Linked to Epic", ep_by), ("Linked to Workshop", ws_by)], links)),
    ])
    return {"Epics": len(epics), "KDDs": len(kdds), "Requirements": len(reqs), "Build Items": len(cfgs),
            "PBIs": len(pbi_list), "Excluded PBIs": len(excluded), "Workshops": len(ws_list), "RAID items": len(raids)}


def build_datasync(data, asof, bhist, path):
    """The DataSync workbook: the cockpit DATA as Excel tables with ID-based links (docs/data_model.md).
    Built from the same data as the cockpit page, so the two always agree."""
    payload = {"data": data, "asof": asof, "burnup_latest_export": asof, "burnup_history": bhist}
    write_workbook(payload, Path(path))
    log("Saved " + path)

# ----- COCKPIT: DATA
def ws_sub(path):
    """Workstream and sub-area, the way the cockpit shows them."""
    parts = [p for p in (path or "").split("\\") if p]
    if len(parts) <= 1:
        return "Unassigned", ("GFPhoenix" if parts else "")
    seg = parts[1]
    rest = "\\".join(parts[2:])
    m = re.match(r"^(O2C|S2P|D2D|M2O|R2R)\b", seg)
    if m:
        return m.group(1), rest
    if re.search(r"OCM", seg, re.I):
        return "OCM", rest
    return "Cross-stream", "\\".join(parts[1:])


def person(x):
    u = x.get("AssignedTo") or {}
    name = u.get("UserName") or ""
    email = (u.get("UserEmail") or "").lower()
    clean = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    text = (name + " " + email).lower()
    if not name:
        return "", "", ""
    if "deloitte" in text:
        return clean, "DL", "Deloitte"
    if "tata" in text or re.search(r"\btcs\b", text) or "tcs.com" in email:
        return clean, "TCS", "TCS"
    if "applied materials" in text or "amat" in email:
        return clean, "AMAT", "Applied Materials"
    if re.search(r"\(ust\b", name.lower()) or "ust.com" in email or "ust-global" in email:
        return clean, "UST", "UST"
    return clean, "GF", "GF"


def resp_party(v):
    t = (v or "").strip().lower()
    if not t:
        return ""
    if "deloitte" in t or t == "dl":
        return "DL"
    if t == "gf" or "global" in t:
        return "GF"
    if "tcs" in t or "tata" in t:
        return "TCS"
    if "ust" in t:
        return "UST"
    if t in ("na", "n/a"):
        return "NA"
    return v


def disposition(v):
    t = (v or "").upper()
    if "GAP" in t:
        return "GAP"
    if "OOB" in t or "OUT OF" in t or "STANDARD" in t:
        return "FIT-OOB"
    if "CFG" in t or "CONFIG" in t:
        return "FIT-CFG"
    return "TBD"


def pbi_series(title):
    pre = (title or "").split(" - ")[0].strip()
    if pre == "CRD":
        return "CRD"
    if pre.startswith("Config & CUT"):
        return "CUT"
    if pre in ("FDD", "FUT"):
        return pre
    if re.search("design", pre, re.I):
        return "TDD"
    if re.search("build", pre, re.I) or re.match(r"^PI ?/ ?PO", pre, re.I):
        return "BUILD"
    return "OCM"


def cockpit_data(ctx):
    """The DATA block of the cockpit page (field order must match cockpit_template.html)."""
    raw, links, wss = ctx["raw"], ctx["links"], ctx["wss"]
    bname = {}
    all_bph = list(raw["bphs"])
    for b in all_bph:
        n = num_of(b.get("Title"))
        if n and n not in bname:
            bname[n] = strip_num(b.get("Title"))

    def label(n, lvl):
        parts = n.split(".") if n else []
        if len(parts) < lvl:
            return "L%d UNKNOWN" % lvl
        k = ".".join(parts[0:lvl])
        return (k + " - " + bname.get(k)) if k in bname else "L%d UNKNOWN" % lvl

    eps = sorted(raw["eps"], key=lambda x: (num_key(num_of(x.get("Title"))), int(sid(x))))
    E, eidx, enum = [], {}, {}
    for x in eps:
        n = num_of(x.get("Title"))
        eidx[sid(x)] = len(E)
        if n:
            enum.setdefault(n, []).append(len(E))
        E.append([n, strip_num(x.get("Title")), label(n, 2), ws_sub(area_of(x))[0], sid(x), 0, label(n, 1), label(n, 3)])

    def ep_of(wid):
        return sorted(eidx[i] for i in links.neighbours(wid) if i in eidx)

    W, widx = [], {}
    for x in sorted(wss, key=lambda z: int(sid(z))):
        widx[sid(x)] = len(W)
        W.append([sid(x), ws_sub(area_of(x))[0], x.get("Title"), x.get("State"), x.get("Custom_ComplexTopic") or "",
                  day(x.get("TargetDate")), ep_of(sid(x))])

    kty, kdec = raw.get("kddType"), raw.get("kddDecided")
    K = []
    for x in sorted(raw["kdds"], key=lambda z: int(sid(z))):
        name, og, firm = person(x)
        if kdec:
            decided = day(x.get(kdec))
        else:
            decided = day(x.get("StateChangeDate")) if x.get("State") == "Approved" else None
        K.append([sid(x), ws_sub(area_of(x))[0], x.get("Title"), x.get("State"), day(x.get("TargetDate")), ep_of(sid(x)),
                  name, "", None, "", decided, (x.get(kty) or "") if kty else "", og])

    cfgs = sorted(raw["cfgs"], key=lambda z: int(sid(z)))
    cidx = dict((sid(x), i) for i, x in enumerate(cfgs))
    pbi_ids = set(sid(x) for x in raw["pbis"])

    Q = []
    for x in sorted(raw["reqs"], key=lambda z: int(sid(z))):
        name, og, firm = person(x)
        nb = links.neighbours(sid(x))
        wlinked = list(w for w in nb if w in widx)
        e = sorted(set(i for w in wlinked for i in W[widx[w]][6]))
        rc = sorted(cidx[c] for c in nb if c in cidx)
        m = re.search(r"(\d+\.\d+\.\d+\.\d+)", x.get("Title") or "")
        byn = enum.get(m.group(1), []) if m else []
        oe, vw = (byn, 0) if byn else (e, 1)
        Q.append([sid(x), ws_sub(area_of(x))[0], x.get("State"), disposition(x.get("Custom_SolutionDispositionPHX")),
                  day(x.get("TargetDate")), e, rc, x.get("Title"), 0 if wlinked else 1, name, oe, vw, og])

    C = []
    for x in cfgs:
        nb = links.neighbours(sid(x))
        fl = ("P" if any(p in pbi_ids for p in nb) else "") + ("E" if any(e in eidx for e in nb) else "")
        direct_epics = sorted(eidx[e] for e in nb if e in eidx)
        is_conversion = 1 if x.get("Custom_TypePHX") == "Conversion" else 0
        C.append([sid(x), "R" if x.get("WorkItemType") == "RICEFW" else "C", x.get("Title"), x.get("State"),
                  ws_sub(area_of(x))[0], day(x.get("TargetDate")), tags_of(x), fl, 0, direct_epics, is_conversion])

    P = []
    for x in sorted(raw["pbis"], key=lambda z: int(sid(z))):
        name, og, firm = person(x)
        parents = sorted(cidx[c] for c in links.neighbours(sid(x)) if c in cidx)
        rc = parents[0] if parents else -1
        rp_code = resp_party(x.get("Custom_ResponsibleParty")) or og
        rp_full = {"DL": "Deloitte", "GF": "GF", "TCS": "TCS", "UST": "UST"}.get(rp_code, rp_code)
        P.append([sid(x), pbi_series(x.get("Title")), x.get("State"), ws_sub(area_of(x))[0], day(x.get("TargetDate")), rc,
                  x.get("Title"), name, "N" if rc < 0 else "", rp_code, rp_full])

    R = []
    for x in sorted(raw["raids"], key=lambda z: int(sid(z))):
        name, og, firm = person(x)
        ws, sub = ws_sub(area_of(x))
        tp = x.get("WorkItemType")
        R.append([sid(x), RAID_LETTER.get(tp, "A"), x.get("Title"), x.get("State"), ws, day(x.get("TargetDate")),
                  name, firm, sub, tags_of(x), tp])

    AL = []
    for w in W:
        for t in sorted(links.neighbours(w[0]), key=int):
            if links.typ.get(t) in RAID_TYPES:
                AL.append([t, w[0]])

    data = {"E": E, "W": W, "K": K, "Q": Q, "C": C, "P": P, "R": R, "AL": AL}
    log("Cockpit data: " + ", ".join("%s=%d" % (k, len(v)) for k, v in data.items()))
    return data


# ----- COCKPIT: PAGE + CHECK
DATE_LABEL = r"\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) 20\d\d\b"
BAD_CHARS = re.compile("\u00c2\u00b7|\u00e2\u20ac")
NAMES = {"E": "L4 Epics", "W": "Workshops", "K": "KDDs", "Q": "Requirements", "C": "Build Items",
         "P": "PBIs", "R": "RAID items", "AL": "RAID-Workshop links"}
REFS = [("W", 6, "E"), ("K", 5, "E"), ("Q", 5, "E"), ("Q", 10, "E"), ("Q", 6, "C"), ("C", 9, "E"), ("P", 5, "C")]
ID_COL = {"E": 4, "W": 0, "K": 0, "Q": 0, "C": 0, "P": 0, "R": 0}


def split_cockpit(text):
    i = text.index("const DATA=") + len("const DATA=")
    data, end = json.JSONDecoder().raw_decode(text, i)
    return text[:i], data, text[end:]


def template_bhist(post):
    b0 = post.index("const BHIST=") + len("const BHIST=")
    b1 = post.index(";const BLAST", b0)
    try:
        return json.loads(post[b0:b1].replace("'", '"'))
    except ValueError:
        return {}


def render_cockpit(template_text, data, asof, bhist):
    """Replaces only the data, the as-of date, the burn-up history and the date labels."""
    pre, old, post = split_cockpit(template_text)
    d = datetime.date.fromisoformat(asof)
    label = "%d %s %d" % (d.day, d.strftime("%b"), d.year)
    pre = re.sub(DATE_LABEL, label, pre)
    post = re.sub(DATE_LABEL, label, post)
    old_asof = re.search(r"const ASOF='(\d{4}-\d\d-\d\d)'", post).group(1)
    post = post.replace("const ASOF='%s'" % old_asof, "const ASOF='%s'" % asof, 1)
    if 'var LAST_REFRESHED = "' in post:
        try:
            refreshed = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(DATA_DIR, "ado_cache.json")))
        except OSError:
            refreshed = datetime.datetime.now()
        post = re.sub(r'(var LAST_REFRESHED = ")[^"]*(";)',
                      lambda m: m.group(1) + refreshed.strftime("%m/%d/%Y %H:%M") + m.group(2), post, count=1)
    b0 = post.index("const BHIST=")
    b1 = post.index(";const BLAST", b0)
    post = post[:b0] + "const BHIST=" + json.dumps(bhist, separators=(",", ":")) + post[b1:]
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return pre + body + post


def _kind(v):
    if v is None:
        return "null"
    if isinstance(v, (bool, int, float)):
        return "number"
    if isinstance(v, list):
        return "list"
    return "text"


def _code_only(pre, post):
    code = pre + "<DATA>" + post
    code = re.sub(r"const ASOF='\d{4}-\d\d-\d\d'", "const ASOF='<ASOF>'", code)
    code = re.sub(r'var LAST_REFRESHED = "[^"]*";', 'var LAST_REFRESHED = "<REFRESHED>";', code)
    b0 = code.index("const BHIST=")
    b1 = code.index(";const BLAST", b0)
    code = code[:b0] + "const BHIST=<BHIST>" + code[b1:]
    return re.sub(DATE_LABEL, "<DATE>", code)


def verify_cockpit(template_text, gen_text):
    """Checks that the generated page is the template with fresh data. Returns (ok, lines)."""
    lines, ok = [], True
    t_pre, t_data, t_post = split_cockpit(template_text)
    g_pre, g_data, g_post = split_cockpit(gen_text)

    t_code, g_code = _code_only(t_pre, t_post), _code_only(g_pre, g_post)
    if t_code == g_code:
        lines.append("CHECK 1  Page code identical to the template ........ PASS")
    else:
        ok = False
        lines.append("CHECK 1  Page code identical to the template ........ FAIL")
        a, b = t_code.splitlines(), g_code.splitlines()
        for n in range(max(len(a), len(b))):
            x = a[n] if n < len(a) else ""
            y = b[n] if n < len(b) else ""
            if x != y:
                lines.append("   first difference at line %d" % (n + 1))
                lines.append("   template : " + x[0:140])
                lines.append("   generated: " + y[0:140])
                break

    problems = []
    for k in t_data:
        tr, gr = t_data.get(k), g_data.get(k)
        if gr is None:
            problems.append("%s: missing" % k)
            continue
        width = len(tr[0]) if tr else None
        short = False
        for r in gr:
            if width is not None and len(r) != width:
                problems.append("%s: rows have %d fields, the template has %d" % (NAMES.get(k, k), len(r), width))
                short = True
                break
        if tr and gr and not short:
            for c in range(width):
                tk = set(_kind(r[c]) for r in tr) - {"null"}
                gk = set(_kind(r[c]) for r in gr) - {"null"}
                if tk and (gk - tk):
                    problems.append("%s field %d holds %s, the template holds %s" % (NAMES.get(k, k), c, sorted(gk), sorted(tk)))
    lines.append("CHECK 2  Data sets, fields and field types ............ " + ("PASS" if not problems else "FAIL"))
    lines.extend("   " + p for p in problems[0:10])
    ok = ok and not problems

    bad = []
    for src, col, dst in REFS:
        size = len(g_data.get(dst, ()))
        for r in g_data.get(src, ()):
            if len(r) <= col:
                continue
            v = r[col]
            for x in (v if isinstance(v, list) else [v]):
                if isinstance(x, int) and x >= size:
                    bad.append("%s %s points to row %d of %s (only %d rows)" % (NAMES.get(src), r[0], x, NAMES.get(dst), size))
    lines.append("CHECK 3  Cross-references point to existing rows ....... " + ("PASS" if not bad else "FAIL"))
    lines.extend("   " + p for p in bad[0:10])
    ok = ok and not bad

    garbled = len(BAD_CHARS.findall(gen_text))
    lines.append("CHECK 4  No corrupted characters ....................... " + ("PASS" if garbled == 0 else "FAIL (%d found)" % garbled))
    ok = ok and garbled == 0

    lines.append("")
    lines.append("   %-22s %10s %10s %18s" % ("Data set", "Template", "Generated", "Template IDs kept"))
    for k in t_data:
        tr, gr = t_data.get(k, []), g_data.get(k, [])
        kept = ""
        if k in ID_COL:
            c = ID_COL.get(k)
            ti = set(str(r[c]) for r in tr)
            gi = set(str(r[c]) for r in gr if len(r) > c)
            kept = "%d of %d" % (len(ti & gi), len(ti)) if ti else ""
        lines.append("   %-22s %10d %10d %18s" % (NAMES.get(k, k), len(tr), len(gr), kept))
    return ok, lines


# ----- PUBLISH + MAIN
def publish(folder, target):
    latest = os.path.join(target, "Latest")
    archive = os.path.join(target, "Archive", os.path.basename(folder))
    os.makedirs(latest, exist_ok=True)
    os.makedirs(os.path.dirname(archive), exist_ok=True)
    shutil.copytree(folder, archive, dirs_exist_ok=True)
    for f in glob.glob(os.path.join(folder, "*.*")):
        fixed = re.sub(r"_\d{4}-\d{2}-\d{2}_\d{6}(?=\.\w+$)", "", os.path.basename(f))
        shutil.copy2(f, os.path.join(latest, fixed))
    log("Published: %s (dated copy in Archive)" % latest)


def main():
    ap = argparse.ArgumentParser(description="Phoenix R6 master program")
    ap.add_argument("--use-cache", action="store_true", help="rebuild from the data saved by the last run")
    ap.add_argument("--out", default=OUTPUT_ROOT, help="folder that receives the dated run folder")
    ap.add_argument("--publish", default=PUBLISH_FOLDER, help="synced SharePoint folder to copy the files into")
    ap.add_argument("--template", default=TEMPLATE, help="cockpit template html")
    ap.add_argument("--skip-excel", action="store_true")
    ap.add_argument("--skip-cockpit", action="store_true")
    args = ap.parse_args()

    template_text = ""
    if not args.skip_cockpit:
        if not os.path.exists(args.template):
            sys.exit("Cockpit template not found: %s\nSave the locked template there, or use --skip-cockpit." % args.template)
        with open(args.template, encoding="utf-8-sig") as fh:
            template_text = fh.read()
        for needle in ("const DATA=", "const ASOF='", "const BHIST=", ";const BLAST"):
            if needle not in template_text:
                sys.exit("The template does not look like the cockpit page (missing %s)." % needle)
        if BAD_CHARS.search(template_text):
            sys.exit("The template contains corrupted characters. Restore cockpit_template.LOCKED.html.")

    os.makedirs(DATA_DIR, exist_ok=True)
    cache = os.path.join(DATA_DIR, "ado_cache.json")
    if args.use_cache:
        if not os.path.exists(cache):
            sys.exit("No saved data yet. Run once without --use-cache.")
        with open(cache, encoding="utf-8") as fh:
            raw = json.load(fh)
        if raw.get("version") != CACHE_VERSION:
            sys.exit("The saved data is from an older version. Run once without --use-cache.")
        log("Loaded saved data (no ADO calls)")
    else:
        pat = os.environ.get("ADO_PAT")
        if not pat:
            sys.exit("ADO_PAT is not set.")
        raw = pull_all(Ado(pat))
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(raw, fh)
        log("Data saved for --use-cache reruns")

    ctx = prepare(raw)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder = os.path.join(args.out, "Phoenix_R6_" + stamp)
    os.makedirs(folder, exist_ok=True)

    # The cockpit page and the DataSync workbook share the data and the burn-up history.
    data = cockpit_data(ctx)
    asof = datetime.date.today().isoformat()
    hist_file = os.path.join(DATA_DIR, "cockpit_bhist.json")
    if os.path.exists(hist_file):
        with open(hist_file, encoding="utf-8") as fh:
            bhist = json.load(fh)
    elif template_text:
        bhist = template_bhist(split_cockpit(template_text)[2])
    else:
        bhist = {}
    done = sorted((p[0] for p in data["P"] if p[2] in DONE_PBI), key=int)
    bhist[asof] = done

    counts = {}
    if not args.skip_excel:
        counts = build_excel(ctx, folder, stamp)
        build_datasync(data, asof, bhist, os.path.join(folder, DATASYNC_FILE))

    all_ok = True
    if not args.skip_cockpit:
        page = render_cockpit(template_text, data, asof, bhist)
        path = os.path.join(folder, "Phoenix R6 Program Cockpit_%s.html" % stamp)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(page)
        with open(hist_file, "w", encoding="utf-8") as fh:
            json.dump(bhist, fh)
        log("Saved " + path)
        print("")
        all_ok, lines = verify_cockpit(template_text, page)
        for line in lines:
            print(line)
        print("")
        print("COCKPIT CHECK: " + ("PASS - same page as the template, with fresh data" if all_ok else "FAIL - see above"))

    if args.publish:
        if all_ok:
            publish(folder, args.publish)
        else:
            print("Not published: the cockpit check failed.")
    print("")
    for k, v in counts.items():
        print("   %-15s %6d" % (k, v))
    print("\nDone in %.0f seconds. Files saved in: %s" % (time.time() - START, folder))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
