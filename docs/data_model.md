# DataSync data model

This is the contract between the layers of the pipeline. The ADO-to-Excel script must produce a workbook that matches it, `excel_to_model.py` turns that workbook into the payload, and the cockpit generator renders the payload.

```
ADO ──► workbook (SharePoint) ──► excel_to_model ──► payload ──► agent ──► generate_cockpit ──► HTML
        tables, id-based links     src/datasync/       JSON       validate   fixed template
```

The code source of truth is `src/datasync/schema.py`. A test fails if a column there is missing from this document.

## The payload

`generate_cockpit.py` fills its template from one JSON object. It has three parts, and only the third comes from the workbook's data sheets.

| Part | Keys | Comes from |
|---|---|---|
| Static text and lists | `title`, `eyebrow_html`, `heading_html`, `lineage`, `hint_*`, `note_*`, `footnotes`, `workstream_order`, `kdd_states`, `raid_*`, `org_*`, `ado_workitem_url`, `burnup_start`, `burnup_end`, `deck_*`, `sources_tag_html` | `config/cockpit_config.json` |
| Per-refresh settings | `asof`, `burnup_latest_export`, `burnup_history` | `Meta` and `Burnup_History` sheets |
| Records | `data.E W K Q C P R AL` | the data sheets below |

## Conventions

- **IDs are text.** ADO IDs such as `193742` are read as text. Numeric cells are accepted and converted, but write them as text to be safe.
- **Dates are ISO** (`2026-10-25`). Real Excel dates are accepted. Blank means no date. Any day/month-swap correction happens before the workbook is written, not in the transform.
- **Links use IDs, never row positions.** A multi-value link cell holds IDs separated by `;`, such as `169370;169375`. The transform turns IDs into the array positions the template needs, so row order in the workbook carries no meaning.
- **Flags** are `0`/`1`. `Y`, `yes`, `true`, `x` also read as 1.
- **Extra columns** are ignored, so the ADO script can add columns without breaking the transform. Required columns must exist under the exact header.
- **Blank rows** inside a table are skipped.

## Workbook sheets

Each sheet holds one Excel table with the name shown. The table must exist, not just the cells.

### `L4_Epics` — table `tblEpics` → `data.E`

One row per L4 business process, joined to its ADO Epic.

| Column | Type | Meaning |
|---|---|---|
| `L4 Number` | text | L4 process number such as `1.1.5.3`. Not unique. |
| `L4 Title` | text | |
| `L2` | text | L2 process name. Blank shows as "L2 UNKNOWN". |
| `Workstream` | text | `O2C`, `S2P`, `D2D`, `M2O`, `R2R`, `OCM`, `Unassigned` or `Cross-stream`. |
| `Epic ID` | key, optional | ADO Epic ID. Unique. Blank only for a BPH-only L4 with no Epic. |
| `BPH Only` | flag | 1 when the L4 exists in the process hierarchy but has no Epic. |
| `L1` | text | L1 process name. |
| `L3` | text | L3 process name. |

### `Workshops` — table `tblWorkshops` → `data.W`

| Column | Type | Meaning |
|---|---|---|
| `Workshop ID` | id | ADO ID. |
| `Workstream` | text | |
| `Title` | text | The phase is read from the title: Initiate, Validate or Align. |
| `State` | text | `Completed` counts as done. `Cancelled` is excluded from scope. |
| `Complex Topic` | text | Blank means "No complex topic". |
| `Target Date` | date | |
| `Epic IDs` | links → Epics | `Epic ID` values. |

### `KDDs` — table `tblKDDs` → `data.K`

| Column | Type | Meaning |
|---|---|---|
| `KDD ID` | id | |
| `Workstream` | text | |
| `Title` | text | |
| `State` | text | One of `kdd_states` in the config. |
| `Target Date` | date | |
| `Epic IDs` | links → Epics | |
| `Assigned To` | text | Owner. A trailing company tag in brackets is stripped for display. |
| `Date Flag` | text | `C` marks a placeholder target date that needs checking. |
| `Check Date` | date | The placeholder date shown when `Date Flag` is `C`. |
| `Reserved` | text | Always blank in the current data. The template does not read it. |
| `Approved Date` | date | When the KDD was approved. |
| `Decision Type` | text | For example `Strategic Decisions` or `Complex Solutioning Decision`. |
| `Org` | text | Owning org code: `GF`, `DL`, and so on. |

### `Requirements` — table `tblRequirements` → `data.Q`

| Column | Type | Meaning |
|---|---|---|
| `Requirement ID` | id | |
| `Workstream` | text | |
| `State` | text | `Rejected` is excluded from counts. |
| `Disposition` | text | `FIT-OOB`, `FIT-CFG`, `GAP` or `TBD`. |
| `Target Date` | date | |
| `Epic IDs` | links → Epics | The requirement's L4 Epics. |
| `Build Item IDs` | links → Build items | Config / RICEFW items that fulfil it. |
| `Title` | text | |
| `No Workshop` | flag | 1 when no workshop is linked. Feeds the "unlinked" views. |
| `Owner` | text | |
| `Origin Epic IDs` | links → Epics | Epics used to count the requirement against an L4 (`qo` in the template). Can differ from `Epic IDs`. |
| `Via Workshop` | flag | 1 when the requirement has no L4 number and is attributed through workshop links. |
| `Org` | text | |

### `Build_Items` — table `tblBuildItems` → `data.C`

Configuration and RICEFW items.

| Column | Type | Meaning |
|---|---|---|
| `Build Item ID` | id | |
| `Type` | text | `C` for Configuration, `R` for RICEFW. |
| `Title` | text | |
| `State` | text | |
| `Workstream` | text | |
| `Target Date` | date | |
| `Tags` | text | `;`-separated tags such as `Boundary Apps`. |
| `Flags` | text | Letters: `P` if the item has PBIs, `E` if it has an Epic. |
| `Not In Build List` | flag | 1 when the item is missing from the build-items export. |

### `PBIs` — table `tblPBIs` → `data.P`

| Column | Type | Meaning |
|---|---|---|
| `PBI ID` | id | |
| `Stage` | text | `CRD`, `CUT`, `FDD`, `FUT` or `BUILD`. |
| `State` | text | `Completed` counts as done. |
| `Workstream` | text | |
| `Target Date` | date | |
| `Build Item ID` | link → Build items | Parent item. Blank means no parent. |
| `Title` | text | |
| `Owner` | text | |
| `Org` | text | |

The "link reason" column the template reads (`N` when the PBI has no parent) is **derived**: the transform sets it, so it is not in the workbook.

### `RAID` — table `tblRAID` → `data.R`

| Column | Type | Meaning |
|---|---|---|
| `RAID ID` | id | |
| `Type` | text | `A` action, `R` risk, `I` issue. |
| `Title` | text | |
| `State` | text | `Completed`, `Closed` and `Archived` count as closed (`raid_closed_states`). |
| `Workstream` | text | |
| `Target Date` | date | Past due means open with a target date before `asof`. |
| `Assigned To` | text | |
| `Firm` | text | `GF`, `Deloitte`, `UST`, `TCS` or `Applied Materials`. |
| `Subcategory` | text | Area subcategory such as `OM` or `PM`. |
| `Tags` | text | `RAID-Critical` marks critical risks and issues. |
| `Type Name` | text | `Action`, `Risk` or `Issue`. |

### `RAID_Workshop_Links` — table `tblRaidWorkshopLinks` → `data.AL`

One row per link from a RAID action to a workshop.

| Column | Type | Meaning |
|---|---|---|
| `RAID ID` | id | May be absent from `RAID`. The cockpit shows these as "not in RAID export". |
| `Workshop ID` | id | Should exist in `Workshops`. Unknown IDs are ignored by the cockpit and flagged as warnings. |

### `Meta` — table `tblMeta`

Key/value settings for the refresh.

| Key | Meaning |
|---|---|
| `asof` | Reporting date. Drives "plan to date" and "past due". |
| `burnup_latest_export` | Date of the latest PBI export. This is the newest point on the burn-up chart. |

### `Burnup_History` — table `tblBurnup` → `burnup_history` (optional)

Completed PBI IDs at past exports. The sheet is optional and the ADO script does not need to write it. The refresh keeps its own history in its state folder (`burnup_history.json`) and adds a snapshot after every run that publishes. The payload's `burnup_history` is the union of three sources: `config/burnup_history_seed.json` (the 18 Oct 2026 snapshot), this sheet if present, and the state folder. The template adds the current export on top, so a same-day re-run replaces that day's point instead of duplicating it.

| Column | Type | Meaning |
|---|---|---|
| `Snapshot Date` | date | Export date. |
| `PBI ID` | id | A PBI that was completed at that date. One row per PBI. |

## Validation

`excel_to_model` writes `validation_report.json` on every run.

**Errors** stop the run and nothing is written: a missing sheet, table or column, a blank or duplicate ID in an ID column, or a missing `Meta` setting.

**Warnings** don't stop the run. The affected cell is fixed up and the warning is reported:

| Case | What the transform does |
|---|---|
| Link ID not found (`Epic IDs`, `Build Item IDs`, `Origin Epic IDs`) | Drops the link |
| Same ID listed twice in a link cell | Drops the duplicate |
| `Build Item ID` not found | Treats the PBI as having no parent |
| Unreadable date | Clears the date |
| Unreadable flag | Sets 0 |
| `Workshop ID` in `RAID_Workshop_Links` not in `Workshops` | Keeps the row |

The agent step reads this report together with the payload.

## Open points

- **Date text in the config.** `note_*`, `footnotes`, `sources_tag_html` and `deck_*` contain hard-coded dates such as "25 Oct 2026". They are copied from the config unchanged, so they go stale on the next refresh. Fix this by templating them from `asof` and the export dates, or by having the agent produce them.
- **Inferred meanings.** `Origin Epic IDs`, `Via Workshop`, `No Workshop`, `Flags` and `Date Flag` / `Check Date` are described from how the template uses them. Confirm them against the ADO query logic when the ADO script is written.
- **Trends and burn-up history need persistent state.** `run_refresh` reads and writes a state folder (past digests, burn-up snapshots). Locally that is `state/`. On Azure it must be storage that survives between runs, or trends and the burn-up history reset on every run.
