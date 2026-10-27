"""Workbook layout and its mapping onto the cockpit DATA blob.

Each Sheet below is one Excel table. The order of its columns is the positional
layout of the matching array in the payload (``data[key]``), which the template
JavaScript reads by index. Change this file and docs/data_model.md together.

Column kinds:
  id       required, unique text key
  key_opt  optional text key, unique when present
  text     free text, blank -> ""
  date     ISO date, blank -> None
  flag     0/1
  ids      ';'-separated ids of another sheet -> list of row indices in that sheet
  ref      single id of another sheet -> row index, or -1 when blank
  derived  computed by the transform, has no workbook column
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Col:
    header: str | None  # None for derived columns
    kind: str
    target: str | None = None  # payload key of the sheet an ids/ref column points at


@dataclass(frozen=True)
class Sheet:
    key: str  # payload key under data{}
    sheet: str
    table: str
    cols: tuple[Col, ...]


SHEETS: tuple[Sheet, ...] = (
    Sheet("E", "L4_Epics", "tblEpics", (
        Col("L4 Number", "text"),
        Col("L4 Title", "text"),
        Col("L2", "text"),
        Col("Workstream", "text"),
        Col("Epic ID", "key_opt"),
        Col("BPH Only", "flag"),
        Col("L1", "text"),
        Col("L3", "text"),
    )),
    Sheet("W", "Workshops", "tblWorkshops", (
        Col("Workshop ID", "id"),
        Col("Workstream", "text"),
        Col("Title", "text"),
        Col("State", "text"),
        Col("Complex Topic", "text"),
        Col("Target Date", "date"),
        Col("Epic IDs", "ids", "E"),
    )),
    Sheet("K", "KDDs", "tblKDDs", (
        Col("KDD ID", "id"),
        Col("Workstream", "text"),
        Col("Title", "text"),
        Col("State", "text"),
        Col("Target Date", "date"),
        Col("Epic IDs", "ids", "E"),
        Col("Assigned To", "text"),
        Col("Date Flag", "text"),
        Col("Check Date", "date"),
        Col("Reserved", "text"),
        Col("Approved Date", "date"),
        Col("Decision Type", "text"),
        Col("Org", "text"),
    )),
    Sheet("Q", "Requirements", "tblRequirements", (
        Col("Requirement ID", "id"),
        Col("Workstream", "text"),
        Col("State", "text"),
        Col("Disposition", "text"),
        Col("Target Date", "date"),
        Col("Epic IDs", "ids", "E"),
        Col("Build Item IDs", "ids", "C"),
        Col("Title", "text"),
        Col("No Workshop", "flag"),
        Col("Owner", "text"),
        Col("Origin Epic IDs", "ids", "E"),
        Col("Via Workshop", "flag"),
        Col("Org", "text"),
    )),
    Sheet("C", "Build_Items", "tblBuildItems", (
        Col("Build Item ID", "id"),
        Col("Type", "text"),
        Col("Title", "text"),
        Col("State", "text"),
        Col("Workstream", "text"),
        Col("Target Date", "date"),
        Col("Tags", "text"),
        Col("Flags", "text"),
        Col("Not In Build List", "flag"),
    )),
    Sheet("P", "PBIs", "tblPBIs", (
        Col("PBI ID", "id"),
        Col("Stage", "text"),
        Col("State", "text"),
        Col("Workstream", "text"),
        Col("Target Date", "date"),
        Col("Build Item ID", "ref", "C"),
        Col("Title", "text"),
        Col("Owner", "text"),
        Col(None, "derived"),  # link reason: "N" when the PBI has no parent build item
        Col("Org", "text"),
    )),
    Sheet("R", "RAID", "tblRAID", (
        Col("RAID ID", "id"),
        Col("Type", "text"),
        Col("Title", "text"),
        Col("State", "text"),
        Col("Workstream", "text"),
        Col("Target Date", "date"),
        Col("Assigned To", "text"),
        Col("Firm", "text"),
        Col("Subcategory", "text"),
        Col("Tags", "text"),
        Col("Type Name", "text"),
    )),
)

# RAID action -> workshop links; emitted as data["AL"] = [[raid_id, workshop_id], ...]
ACTION_LINKS = Sheet("AL", "RAID_Workshop_Links", "tblRaidWorkshopLinks", (
    Col("RAID ID", "id"),
    Col("Workshop ID", "id"),
))

# Key/value settings that change per refresh: Key, Value
META_SHEET, META_TABLE = "Meta", "tblMeta"
META_KEYS = ("asof", "burnup_latest_export")

# Burn-up snapshots: completed PBI ids per export date -> burnup_history
BURNUP_SHEET, BURNUP_TABLE = "Burnup_History", "tblBurnup"
BURNUP_HEADERS = ("Snapshot Date", "PBI ID")
