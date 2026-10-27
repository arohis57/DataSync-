# Power Automate flows

The Azure job does no SharePoint work itself. It calls two Power Automate flows over HTTP, the same way TaskLens posts to its Teams flow. Nothing here has been run in Power Automate yet. The job side is tested against a local stand-in (`scripts/mock_flows.py`), so build the flows to this contract and check each expression in the flow's run history.

```
Azure job ──POST──► Flow 1 "Get inputs"  ──► returns workbook + saved state
Azure job ──POST──► Flow 2 "Publish"     ──► uploads dashboard + state, sends the email
```

Both URLs contain a signature. Treat them as secrets: keep them in `.env` / Container Apps secrets, never in git or logs. Regenerating the trigger URL invalidates the old one.

## SharePoint layout (suggested)

```
Shared Documents/DataSync/
  input/    Phoenix_R6_DataSync.xlsx          written by the ADO-to-Excel script
  output/   Phoenix R6 Program Cockpit.html    written by Flow 2
  state/    datasync_state.json                written by Flow 2, read by Flow 1
```

## Flow 1: "DataSync - Get inputs"

1. **Trigger:** *When an HTTP request is received* (method POST, no schema needed).
2. **Get file content using path** (SharePoint), name it `Get workbook`: the workbook path.
3. **Get file content using path**, name it `Get state`: `state/datasync_state.json`. Under *Configure run after* on the next step, tick **is successful** and **has failed**, so a missing file on the first run doesn't stop the flow.
4. **Response**, status 200, header `Content-Type: application/json`, body:

```json
{
  "workbook_b64": "@{body('Get_workbook')?['$content']}",
  "state_b64": "@{coalesce(outputs('Get_state')?['body/$content'], '')}"
}
```

`$content` is the file as base64. Check in the run history that `workbook_b64` is a long base64 string, not an object. The job needs `workbook_b64` non-empty; `state_b64` may be empty (first run).

The response must come back within 2 minutes. The workbook is well under that.

## Flow 2: "DataSync - Publish"

**Trigger:** *When an HTTP request is received*, with this body schema:

```json
{
  "type": "object",
  "properties": {
    "status":     {"type": "string"},
    "publish":    {"type": "boolean"},
    "asof":       {"type": ["string", "null"]},
    "reason":     {"type": "string"},
    "subject":    {"type": "string"},
    "email_html": {"type": "string"},
    "email_text": {"type": "string"},
    "to":         {"type": "array", "items": {"type": "string"}},
    "cc":         {"type": "array", "items": {"type": "string"}},
    "dashboard":  {"type": ["object", "null"], "properties": {"filename": {"type": "string"}, "content_b64": {"type": "string"}}},
    "state_b64":  {"type": ["string", "null"]}
  }
}
```

| Field | Meaning |
|---|---|
| `publish` | `true` only for PASS and WARNING runs. When `false`, `dashboard` and `state_b64` are `null`: upload nothing. |
| `dashboard` | The HTML file, about 1.7 MB (2.3 MB as base64). `filename` is built from the dashboard title. |
| `state_b64` | The saved state for the next run, about 10 KB. Present only when `publish` is true. |
| `subject`, `email_html` | The report email. Sent every run, including blocked ones and "refresh failed" notices. |
| `to`, `cc` | Taken from the job's `DATASYNC_EMAIL_TO` / `DATASYNC_EMAIL_CC`. May be empty; the flow then uses its own fixed list. |

**Actions:**

1. **Condition:** `publish` is equal to `true`. If yes:
   1. Upload the dashboard to `output/`. SharePoint's *Create file* fails when the file already exists, so use **Get file metadata using path**, then a condition on whether it succeeded: *Update file* (file identifier from the metadata) if yes, *Create file* if no. File content: `base64ToBinary(triggerBody()?['dashboard']?['content_b64'])`. File name: `triggerBody()?['dashboard']?['filename']`.
   2. Do the same for `state/datasync_state.json`, with content `base64ToBinary(triggerBody()?['state_b64'])`.
2. **Send an email (V2)** (Office 365 Outlook), after the condition, outside both branches so it runs every time:
   - To: `join(triggerBody()?['to'], ';')`, or your fixed list when that is empty.
   - Subject: `triggerBody()?['subject']`
   - Body: `triggerBody()?['email_html']`, with *Is HTML* set to Yes.
3. **Response**, status 200, body `{"ok": true}`.

If this flow fails, the job exits non-zero and does not retry. A retry could send the email twice.

## Testing without the flows

```
python scripts/mock_flows.py samples/Phoenix_R6_DataSync.xlsx --dir mock_sharepoint
# second terminal
set DATASYNC_INPUT_URL=http://localhost:8788/in
set DATASYNC_PUBLISH_URL=http://localhost:8788/out
set DATASYNC_NO_AGENT=1
python -m datasync.job
```

After you build the real flows, call Flow 1 once with curl or Postman and check the response, then run the job with `DATASYNC_NO_AGENT=1` before turning the AI step on.
