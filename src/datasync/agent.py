"""The DataSync agent step: send the digest to Claude, get a validated assessment back.

The system prompt is src/DataSync_prompt.md, unchanged. The code adds what the prompt doesn't say:
the agent sees a digest, not the raw records, and must not invent figures or trends.

Usage:  python -m datasync.agent [--payload P.json] [--report R.json] [--previous D.json] [--dry-run]

--dry-run builds the digest and the request but does not call the API.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic

from .digest import build_digest

ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = ROOT / "src" / "DataSync_prompt.md"
BUILD = ROOT / "build"

MODEL = os.environ.get("DATASYNC_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("DATASYNC_EFFORT", "medium")
MAX_TOKENS = 8000
FALLBACK_BETA = "server-side-fallback-2026-07-01"  # re-runs a safety-declined request on another model

STATUSES = ("PASS", "WARNING", "FAIL")
SEVERITY = {s: i for i, s in enumerate(STATUSES)}

_STRINGS = {"type": "array", "items": {"type": "string"}}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": list(STATUSES)},
        "validationSummary": {
            "type": "object",
            "properties": {"missingValues": _STRINGS, "duplicateRecords": _STRINGS, "dataQualityIssues": _STRINGS},
            "required": ["missingValues", "duplicateRecords", "dataQualityIssues"],
            "additionalProperties": False,
        },
        "metricsSummary": {
            "type": "object",
            "properties": {k: {"type": "string"} for k in ("requirements", "risks", "actions", "overallHealth")},
            "required": ["requirements", "risks", "actions", "overallHealth"],
            "additionalProperties": False,
        },
        "executiveSummary": _STRINGS,
        "publishRecommendation": {"type": "string"},
    },
    "required": ["status", "validationSummary", "metricsSummary", "executiveSummary", "publishRecommendation"],
    "additionalProperties": False,
}

INPUT_CONTRACT = """\
Below is today's DataSync digest for the Phoenix Program Cockpit, as JSON. It was computed from the \
validated workbook; you do not receive the raw records, and the dashboard payload itself is already built, so \
do not try to reproduce it. Return only the JSON assessment in the output format you were given.

How to use it:
- Use only figures that appear in the digest. Do not estimate or invent numbers, names or causes.
- `kpi_changes` is null when there is no earlier refresh to compare with. In that case do not describe \
trends, increases or decreases.
- `definitions` says exactly how each measure is counted. Quote record ids from the `sample_ids` / \
`*_ids` fields when you point at records that need manual review.
- Set status FAIL only when the data is not reliable enough to publish, WARNING when it can be published \
but something needs attention, PASS otherwise.
- executiveSummary: 3 to 5 short bullets for program leadership, most important first.

Digest:
"""


@dataclass
class AgentResult:
    assessment: dict | None  # None when the call or the answer was unusable
    error: str | None = None
    request_id: str | None = None
    model: str | None = None
    usage: dict | None = None
    skipped: bool = False  # the step was switched off, which is not a failure

    @property
    def status(self) -> str:
        if self.skipped:
            return "PASS"
        return self.assessment["status"] if self.assessment else "FAIL"


def load_prompt(path: Path = PROMPT_PATH) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"{path} is empty")
    return text


def build_request(digest: dict, prompt: str, model: str = MODEL, effort: str = EFFORT, fallbacks: bool = True) -> dict:
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": prompt,
        "messages": [{"role": "user", "content": INPUT_CONTRACT + json.dumps(digest, ensure_ascii=False, indent=1)}],
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
    }
    if fallbacks:
        body["betas"] = [FALLBACK_BETA]
        body["fallbacks"] = "default"
    return body


CLI_MODEL = os.environ.get("DATASYNC_CLI_MODEL", "sonnet")
CLI_TIMEOUT = 600


def cli_command(prompt: str, model: str = CLI_MODEL) -> list[str]:
    """Headless Claude Code, same way TaskLens runs it. No tools: the agent only reads the digest it is given."""
    return ["claude", "-p", "--model", model, "--system-prompt", prompt, "--output-format", "json",
            "--json-schema", json.dumps(SCHEMA), "--tools", "", "--disable-slash-commands", "--no-session-persistence"]


def parse_cli_output(stdout: str) -> tuple[dict | None, str | None, dict]:
    """(assessment, error, meta) from `claude -p --output-format json`."""
    try:
        env = json.loads(stdout)
    except json.JSONDecodeError:
        return None, "claude output is not JSON", {}
    if isinstance(env, list):  # some versions emit the event list; the last 'result' event is the answer
        env = next((e for e in reversed(env) if isinstance(e, dict) and e.get("type") == "result"), None)
    if not isinstance(env, dict):
        return None, "claude output has no result", {}
    meta = {"request_id": env.get("session_id"), "usage": {**(env.get("usage") or {}), "total_cost_usd": env.get("total_cost_usd")}}
    if env.get("is_error"):
        return None, f"claude reported an error: {str(env.get('result'))[:300]}", meta
    answer = env.get("structured_output")
    if answer is None:
        text = str(env.get("result") or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)  # tolerate a fenced answer
        try:
            answer = json.loads(text)
        except json.JSONDecodeError as e:
            return None, f"answer is not valid JSON: {e}", meta
    problem = check_assessment(answer)
    return (None, problem, meta) if problem else (answer, None, meta)


def run_agent_cli(digest: dict, *, prompt: str | None = None, model: str = CLI_MODEL, runner=subprocess.run) -> AgentResult:
    """Run the agent through the `claude` CLI (auth: CLAUDE_CODE_OAUTH_TOKEN). Never raises for run or answer problems."""
    message = INPUT_CONTRACT + json.dumps(digest, ensure_ascii=False, indent=1)
    try:
        proc = runner(cli_command(prompt or load_prompt(), model), input=message, capture_output=True, text=True,
                      encoding="utf-8", errors="replace", timeout=CLI_TIMEOUT)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return AgentResult(None, f"could not run claude: {type(e).__name__}: {e}")
    if proc.returncode != 0:
        return AgentResult(None, f"claude exited {proc.returncode}: {(proc.stderr or proc.stdout or '').strip()[-300:]}", model=model)
    assessment, error, meta = parse_cli_output(proc.stdout or "")
    return AgentResult(assessment, error, model=model, **meta)


def analyze(digest: dict, *, backend: str | None = None, client=None, **opts) -> AgentResult:
    """Pick the backend: `cli` (Claude Code token, as in TaskLens) or `api` (Anthropic SDK + ANTHROPIC_API_KEY).

    Order: an explicit backend, then DATASYNC_AGENT_BACKEND, then `api` if a client was supplied,
    then `cli` when CLAUDE_CODE_OAUTH_TOKEN is set, else `api`.
    """
    backend = backend or os.environ.get("DATASYNC_AGENT_BACKEND") or (
        "api" if client is not None else "cli" if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") else "api")
    if backend == "cli":
        return run_agent_cli(digest, **({"model": opts["model"]} if opts.get("model") else {}))
    if backend == "api":
        return run_agent(digest, client=client, **opts)
    raise ValueError(f"unknown agent backend {backend!r} (use 'cli' or 'api')")


def check_assessment(a: Any) -> str | None:
    """Why an answer is unusable, or None. The schema is enforced by the API; this guards the rest."""
    if not isinstance(a, dict):
        return "answer is not a JSON object"
    if a.get("status") not in STATUSES:
        return f"status {a.get('status')!r} is not one of {STATUSES}"
    n = len(a.get("executiveSummary", []))
    if not 3 <= n <= 5:
        return f"executiveSummary has {n} bullets, expected 3 to 5"
    if not a.get("publishRecommendation", "").strip():
        return "publishRecommendation is empty"
    return None


def run_agent(digest: dict, *, client: anthropic.Anthropic | None = None, prompt: str | None = None, **opts) -> AgentResult:
    """Call the model. Never raises for API or answer problems: they come back as an AgentResult with an error."""
    request = build_request(digest, prompt or load_prompt(), **opts)
    client = client or anthropic.Anthropic()
    try:
        resp = client.beta.messages.create(**request) if "betas" in request else client.messages.create(**request)
    except anthropic.APIError as e:
        return AgentResult(None, f"{type(e).__name__}: {getattr(e, 'message', e)}")

    meta = {"request_id": getattr(resp, "_request_id", None), "model": getattr(resp, "model", None),
            "usage": resp.usage.to_dict() if hasattr(getattr(resp, "usage", None), "to_dict") else None}
    if resp.stop_reason == "refusal":
        return AgentResult(None, "the model declined the request (refusal)", **meta)
    if resp.stop_reason == "max_tokens":
        return AgentResult(None, "the answer was cut off at max_tokens", **meta)
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        assessment = json.loads(text)
    except json.JSONDecodeError as e:
        return AgentResult(None, f"answer is not valid JSON: {e}", **meta)
    problem = check_assessment(assessment)
    if problem:
        return AgentResult(None, problem, **meta)
    return AgentResult(assessment, None, **meta)


def gate(result: AgentResult, report: dict) -> dict:
    """Decide whether to publish. The agent can make the status stricter but never more lenient than the checks in code."""
    floor = "FAIL" if report.get("errors") else "WARNING" if report.get("warnings") else "PASS"
    status = max(result.status, floor, key=SEVERITY.get)
    if result.skipped:
        reason = "agent step skipped; decided on workbook validation only"
    elif result.error:
        reason = f"agent step failed: {result.error}"
    elif status != result.status:
        reason = f"raised from {result.status} to {status} by workbook validation"
    else:
        reason = "agent assessment"
    return {"status": status, "publish": status != "FAIL", "reason": reason}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the DataSync agent on a payload.")
    ap.add_argument("--payload", type=Path, default=BUILD / "cockpit_data.json")
    ap.add_argument("--report", type=Path, default=BUILD / "validation_report.json")
    ap.add_argument("--previous", type=Path, help="digest.json from the previous refresh, for trends")
    ap.add_argument("--out-dir", type=Path, default=BUILD)
    ap.add_argument("--model", help="api backend: model id (default claude-opus-5-5); cli backend: alias such as sonnet")
    ap.add_argument("--backend", choices=("cli", "api"), help="default: DATASYNC_AGENT_BACKEND, else cli if CLAUDE_CODE_OAUTH_TOKEN is set")
    ap.add_argument("--no-fallbacks", action="store_true", help="api backend: don't opt in to server-side refusal fallbacks")
    ap.add_argument("--dry-run", action="store_true", help="build the digest and request, don't call the API")
    args = ap.parse_args(argv)

    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    previous = json.loads(args.previous.read_text(encoding="utf-8")) if args.previous else None
    digest = build_digest(payload, report, previous)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "digest.json").write_text(json.dumps(digest, ensure_ascii=False, indent=1), encoding="utf-8")

    if args.dry_run:
        req = build_request(digest, load_prompt(), args.model or MODEL, fallbacks=not args.no_fallbacks)
        print(f"dry run: request ~{len(json.dumps(req)) // 1000} KB; digest written to {args.out_dir / 'digest.json'}")
        return 0

    opts = {"model": args.model} if args.model else {}
    result = analyze(digest, backend=args.backend, fallbacks=not args.no_fallbacks, **opts)
    decision = gate(result, report)
    out = {"decision": decision, "assessment": result.assessment, "error": result.error,
           "request_id": result.request_id, "model": result.model, "usage": result.usage}
    (args.out_dir / "agent_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"status={decision['status']} publish={decision['publish']} ({decision['reason']}) -> {args.out_dir / 'agent_result.json'}")
    return 0 if decision["publish"] else 1


if __name__ == "__main__":
    sys.exit(main())
