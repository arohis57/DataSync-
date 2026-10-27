"""Local stand-in for the two Power Automate flows, to run datasync.job end to end without Azure.

  python scripts/mock_flows.py WORKBOOK.xlsx [--dir mock_sharepoint] [--port 8788]

  POST /in   -> returns the workbook and the saved state (like the "Get inputs" flow)
  POST /out  -> saves the dashboard, state and email into --dir (like the "Publish" flow)

Then, in another terminal:
  set DATASYNC_INPUT_URL=http://localhost:8788/in
  set DATASYNC_PUBLISH_URL=http://localhost:8788/out
  set DATASYNC_NO_AGENT=1
  python -m datasync.job
"""
import argparse
import base64
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("workbook", type=Path)
ap.add_argument("--dir", type=Path, default=Path("mock_sharepoint"))
ap.add_argument("--port", type=int, default=8788)
args = ap.parse_args()
args.dir.mkdir(parents=True, exist_ok=True)
STATE = args.dir / "datasync_state.json"


class Handler(BaseHTTPRequestHandler):
    def _reply(self, obj) -> None:
        raw = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        if self.path == "/in":
            state = base64.b64encode(STATE.read_bytes()).decode() if STATE.exists() else ""
            self._reply({"workbook_b64": base64.b64encode(args.workbook.read_bytes()).decode(), "state_b64": state})
            print("served inputs", "(with saved state)" if state else "(first run, no state)")
            return
        (args.dir / "email.html").write_text(body["email_html"], encoding="utf-8")
        print(f"email: {body['subject']}  to={body['to']}")
        if body["dashboard"]:
            (args.dir / body["dashboard"]["filename"]).write_bytes(base64.b64decode(body["dashboard"]["content_b64"]))
            STATE.write_bytes(base64.b64decode(body["state_b64"]))
            print(f"saved {body['dashboard']['filename']} and state")
        else:
            print("not published: dashboard and state left as they were")
        self._reply({"ok": True})

    def log_message(self, *a) -> None:
        pass


print(f"mock flows on http://localhost:{args.port}, saving to {args.dir}")
HTTPServer(("localhost", args.port), Handler).serve_forever()
