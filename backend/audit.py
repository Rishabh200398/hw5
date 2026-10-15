"""Append-only audit trail of the agent team: output/audit_trail.json.

Each line is one JSON record (JSON Lines). The file is only ever opened in append
mode, so earlier records are never rewritten or wiped, not even by a database
reset. Every record has the time, the run_id and an event type:

  run_start      - model, loop limits, which MCP tools each agent may call, the prompt
  agent_run      - one agent's run: who, for which ticket, who asked, depth, the
                   question, its typed output, tokens used and how it stopped
  tool_call      - every MCP tool call: agent, tool, args, result
  delegate / report / payment_request / draft / tool_request / decision / refused
                 - every step a human watching the board would want to replay
  human_action   - a human approving or rejecting something on the dashboard
  run_end        - stop reason, total requests and tokens
"""

import json
from datetime import datetime, timezone
from pathlib import Path

AUDIT_PATH = Path(__file__).resolve().parent.parent / "output" / "audit_trail.json"
MAX_FIELD = 2000  # long values are cut so one run can't bloat the trail


def _clip(value):
    """Keep structured values, but cut very long strings."""
    if isinstance(value, str) and len(value) > MAX_FIELD:
        return value[: MAX_FIELD - 1] + "…"
    if isinstance(value, dict):
        return {k: _clip(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clip(v) for v in value]
    return value


def append(run_id: str, event: str, **fields) -> None:
    """Add one record to the end of the audit trail. Never raises."""
    record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "run_id": run_id, "event": event, **_clip(fields)}
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass  # never let logging break a run
