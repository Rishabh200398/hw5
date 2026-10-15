"""Campus Customs backend: FastAPI routes the dashboard calls.

Shop facts (tickets, cash) are read through the campus-customs MCP server, never
straight from the database. Payments happen only when a human approves one here.

Routes (all under /api):
  GET  /tickets                        - every ticket and whether it's open or resolved
  POST /tickets/{ticket_id}/run        - run the agent team on one ticket (in the background)
  GET  /events?after=N                 - agent events since event N, for the board to refresh
  POST /payments/{request_id}/approve  - a human approves a payment or purchase order
  GET  /cash                           - current checking balance from cash_accounts
  POST /reset                          - reset the working database to the original
Plus, for the dashboard:
  GET  /board                          - what's waiting for a human (payments, drafts, tool requests)
  POST /payments/{request_id}/reject   - a human rejects a payment request
  POST /discounts/{discount_id}/approve - a human approves a customer discount
  POST /discounts/{discount_id}/reject  - a human rejects a customer discount
  POST /drafts/{draft_id}/approve      - a human approves a customer draft (never sent)
  POST /drafts/{draft_id}/reject       - a human rejects a customer draft

Run from backend/:  ../.venv/bin/uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import shutil

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import audit
import team
from models import PaymentRequest

ORIGINAL_DB = team.ROOT / "data" / "campus_customs.db"
WORKING_DB = team.ROOT / "data" / "campus_customs_new.db"

app = FastAPI(title="Campus Customs Multi-Agent Operations")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # the Vite dashboard
    allow_methods=["*"],
    allow_headers=["*"],
)

# The board the dashboard watches. It lives until the next reset, so runs on different
# tickets share one view of what's waiting for the human.
BOARD = team.new_board()
_running: asyncio.Task | None = None


def _busy() -> bool:
    return _running is not None and not _running.done()


async def _mcp(tool: str, args: dict | None = None):
    """Call one campus-customs MCP tool and return its result."""
    async with team.mcp_client() as client:
        result = await client.call_tool(tool, args or {}, raise_on_error=False)
    data = result.structured_content or {}
    return data.get("result", data)  # FastMCP wraps list results in {"result": [...]}


# ---------------------------------------------------------------- 1. tickets


@app.get("/api/tickets")
async def list_tickets() -> list[dict]:
    """Every ticket and whether it's open or resolved, plus the Boss's latest decision."""
    tickets = await _mcp("list_tickets")
    out = []
    for t in tickets:
        decision = BOARD.run.decisions.get(t["id"])
        out.append({
            "id": t["id"], "type": t["type"], "requester": t["requester"], "subject": t["subject"],
            "sku": t["sku"], "size": t["size"], "qty": t["qty"],
            "lease_id": t["lease_id"], "invoice_id": t["invoice_id"], "notes": t["notes"],
            "status": t["status"],  # from the database: open / resolved
            "team_status": decision.status if decision else None,  # e.g. waiting_on_human
            "decision": decision.model_dump() if decision else None,
        })
    return out


# ---------------------------------------------------------------- 2. run the team


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int) -> dict:
    """Start the agent team on one ticket. Returns at once; watch /api/events for progress."""
    global _running
    if _busy():
        raise HTTPException(409, f"Run {BOARD.run.current_run} is still in progress.")
    ticket = next((t for t in await _mcp("list_tickets") if t["id"] == ticket_id), None)
    if ticket is None:
        raise HTTPException(404, f"No ticket {ticket_id}.")
    if ticket["status"] == "resolved":
        raise HTTPException(409, f"Ticket {ticket_id} is already resolved.")
    first_event = len(BOARD.run.events) + 1
    _running = asyncio.create_task(team.run_team(BOARD, ticket_id))
    await asyncio.sleep(0)  # let the run start and claim its run id
    return {"status": "started", "ticket_id": ticket_id, "run_id": BOARD.run.current_run,
            "events_from": first_event}


# ---------------------------------------------------------------- 3. events


@app.get("/api/events")
async def events(after: int = 0, limit: int = 200) -> dict:
    """Agent events after event number `after`: who did what, what they said, which tool they used."""
    new = [e for e in BOARD.run.events if e.id > after][:limit]
    return {
        "running": _busy(),
        "current_run": BOARD.run.current_run,
        "last_event": BOARD.run.events[-1].id if BOARD.run.events else 0,
        "events": [e.model_dump() for e in new],
    }


# ---------------------------------------------------------------- 4. human approval


class Approval(BaseModel):
    approved_by: str = Field(min_length=1, description="Name of the human approving.")


def _payment(request_id: int) -> PaymentRequest:
    request = next((p for p in BOARD.run.payment_requests if p.id == request_id), None)
    if request is None:
        raise HTTPException(404, f"No payment request {request_id}.")
    if request.status != "pending":
        raise HTTPException(409, f"Payment request {request_id} is already {request.status}.")
    return request


@app.post("/api/payments/{request_id}/approve")
async def approve_payment(request_id: int, body: Approval) -> dict:
    """A human clicked Approve: only now is make_payment called, over MCP."""
    if not body.approved_by.strip():
        raise HTTPException(422, "approved_by is required.")
    _payment(request_id)
    request = await team.approve_payment(BOARD, request_id, body.approved_by.strip())
    paid = request.status == "approved"
    if not paid:  # make_payment refused: e.g. not enough cash, or the vendor is still blocked
        raise HTTPException(409, {"paid": False, "request": request.model_dump()})
    return {"paid": True, "request": request.model_dump(), "cash": request.result.get("cash")}


@app.post("/api/payments/{request_id}/reject")
async def reject_payment(request_id: int, body: Approval) -> dict:
    """A human clicked Reject. Nothing is paid, and the request's cash is freed up."""
    _payment(request_id)
    team.reject(BOARD, request_id, body.approved_by.strip())
    return {"rejected": True, "request_id": request_id}


@app.post("/api/discounts/{discount_id}/approve")
async def approve_discount(discount_id: int, body: Approval) -> dict:
    """A human approves a discount for a customer (no money moves; it sets the price offered)."""
    discount = next((d for d in BOARD.run.discount_requests if d.id == discount_id), None)
    if discount is None:
        raise HTTPException(404, f"No discount {discount_id}.")
    if discount.status != "pending":
        raise HTTPException(409, f"Discount {discount_id} is already {discount.status}.")
    discount = await team.approve_discount(BOARD, discount_id, body.approved_by.strip())
    return {"approved": True, "discount": discount.model_dump()}


@app.post("/api/discounts/{discount_id}/reject")
async def reject_discount(discount_id: int, body: Approval) -> dict:
    """A human rejects a discount. The ticket stays open so the team can rethink the offer."""
    if not any(d.id == discount_id and d.status == "pending" for d in BOARD.run.discount_requests):
        raise HTTPException(404, f"No pending discount {discount_id}.")
    team.reject(BOARD, discount_id, body.approved_by.strip())
    return {"rejected": True, "discount_id": discount_id}


@app.post("/api/drafts/{draft_id}/approve")
async def approve_draft(draft_id: int, body: Approval) -> dict:
    """A human approves a customer draft. It is marked approved but never sent."""
    draft = next((d for d in BOARD.run.drafts if d.id == draft_id), None)
    if draft is None:
        raise HTTPException(404, f"No draft {draft_id}.")
    if draft.status != "pending":
        raise HTTPException(409, f"Draft {draft_id} is already {draft.status}.")
    draft = await team.approve_draft(BOARD, draft_id, body.approved_by.strip())
    return {"approved": True, "draft": draft.model_dump()}


@app.post("/api/drafts/{draft_id}/reject")
async def reject_draft(draft_id: int, body: Approval) -> dict:
    """A human rejects a customer draft. The ticket stays open so the team can try again."""
    if not any(d.id == draft_id and d.status == "pending" for d in BOARD.run.drafts):
        raise HTTPException(404, f"No pending draft {draft_id}.")
    team.reject(BOARD, draft_id, body.approved_by.strip())
    return {"rejected": True, "draft_id": draft_id}


@app.get("/api/board")
async def board() -> dict:
    """Everything waiting for (or decided by) a human, and the Boss's latest decisions."""
    run = BOARD.run
    return {
        "board_id": run.run_id,
        "running": _busy(),
        "payment_requests": [p.model_dump() for p in run.payment_requests],
        "cash_committed_to_pending": round(sum(p.amount for p in run.payment_requests if p.status == "pending"), 2),
        "discount_requests": [d.model_dump() for d in run.discount_requests],
        "drafts": [d.model_dump() for d in run.drafts],
        "tool_requests": [t.model_dump() for t in run.tool_requests],
        "decisions": {k: v.model_dump() for k, v in run.decisions.items()},
        "model_requests": run.model_requests,
    }


# ---------------------------------------------------------------- 5. cash


@app.get("/api/cash")
async def cash() -> dict:
    """Current checking balance, read from cash_accounts through MCP."""
    return await _mcp("get_cash_balance", {"account": "checking"})


# ---------------------------------------------------------------- 6. reset


@app.post("/api/reset")
async def reset() -> dict:
    """Copy the original database over the working copy and start a clean board.

    The original file is only read, and the audit trail is never wiped.
    """
    global BOARD
    if _busy():
        raise HTTPException(409, "Can't reset while a run is in progress.")
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    old_board = BOARD.run.run_id
    BOARD = team.new_board()
    audit.append(BOARD.run.run_id, "db_reset", copied_from=ORIGINAL_DB.name, copied_to=WORKING_DB.name,
                 previous_board=old_board)
    return {"reset": True, "board_id": BOARD.run.run_id, "cash": await cash(),
            "open_tickets": len(await _mcp("list_open_tickets"))}
