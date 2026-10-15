"""The Campus Customs agent team (PydanticAI): Boss, Inventory, Accounting,
Facilities and Customer Service.

Pieces:
  prompts/*.md     - each agent's prompt + the shared shop_rules.md
  models.py        - typed reports, decisions and the things that wait for a human
  model_config.py  - gpt-6-luna through Portkey (the only model allowed)
  team.py          - this file: the agents, delegation and the agent loop

Shop facts come only from the campus-customs MCP server (.mcp.json), which reads
data/campus_customs_new.db. Agents never get make_payment: they *prepare* payment
requests, and only a human's approval (approve_payment) calls it, over MCP.

Agent loop:
  run_board() starts the Boss on the whole board. The Boss delegates with the
  `delegate` tool; any agent may delegate to any other (full connectivity), so a
  delegation simply runs the other agent and returns its typed report. Limits:
    MAX_DEPTH                  - longest chain of handoffs (Boss -> A -> B -> C)
    MAX_DELEGATIONS_PER_TICKET - handoffs per ticket across the whole run
    REQUEST_LIMIT              - model requests for the whole run (all agents share it)
  and no ping-pong: an agent can't delegate to anyone already in its request chain.

Run from backend/:  ../.venv/bin/python team.py
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from fastmcp import Client
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.toolsets import WrapperToolset
from pydantic_ai.usage import UsageLimits

import audit
from model_config import MODEL_NAME, build_model
from models import (
    AgentName,
    AgentReport,
    BoardPlan,
    BoardRun,
    CustomerDraft,
    DiscountRequest,
    Fact,
    PaymentRequest,
    TeamEvent,
    Teammate,
    ToolRequest,
)
from prompts import instructions_for

ROOT = Path(__file__).resolve().parent.parent
MCP_CONFIG = ROOT / ".mcp.json"

# Agent loop limits (documented in output/harness.md). All agents working one ticket share one
# usage counter, so these cap the whole ticket, not each agent.
MAX_DEPTH = 3                    # longest chain of handoffs
MAX_DELEGATIONS_PER_TICKET = 8   # handoffs per ticket
# Budgets are per ticket: a prerequisite ticket solved with solve_ticket_first gets its own.
REQUEST_LIMIT = 80               # model requests per ticket
TOOL_CALLS_LIMIT = 120           # tool calls per ticket
TOTAL_TOKENS_LIMIT = 400_000     # input + output tokens per ticket (shop rule 28)
MAX_TOKENS_PER_REPLY = 16_000    # cap on each model reply (reasoning tokens count towards it)
# Enough reasoning to plan and do the cash arithmetic, without burning tokens. Customer Service
# only writes from facts it is handed, and at "low" it once ran past the reply cap after drafting.
REASONING_EFFORT = {"customer_service": "none"}
LIMITS = UsageLimits(request_limit=REQUEST_LIMIT, tool_calls_limit=TOOL_CALLS_LIMIT,
                     total_tokens_limit=TOTAL_TOKENS_LIMIT)

# MCP tools each agent may call. New tools are added here only after the human approves
# them and they are added to the MCP server (shop rule 18).
MCP_TOOLS: dict[str, set[str]] = {
    "boss": {"list_open_tickets", "resolve_ticket"},
    "inventory": {"check_stock", "check_vendor_can_ship", "list_vendors"},
    "accounting": {"get_cash_balance", "get_pricing", "check_vendor_can_ship", "list_vendors", "get_lease"},
    "facilities": {"get_lease"},
    "customer_service": set(),  # gets confirmed facts from teammates, never raw shop data
}
HUMAN_ONLY_TOOLS = {"make_payment"}  # never given to an agent, whatever MCP_TOOLS says

DISPLAY = {
    "boss": "Boss",
    "inventory": "Inventory",
    "accounting": "Accounting",
    "facilities": "Facilities",
    "customer_service": "Customer Service",
}


def mcp_client() -> Client:
    """A FastMCP client for the campus-customs server, from the project's .mcp.json.

    .mcp.json uses paths relative to the project root (so it works on any machine);
    they are resolved here so the backend can start the server from any folder.
    """
    config = json.loads(MCP_CONFIG.read_text())
    for server in config["mcpServers"].values():
        if not Path(server["command"]).is_absolute() and "/" in server["command"]:
            server["command"] = str(ROOT / server["command"])
        server["args"] = [str(ROOT / a) if a.endswith(".py") and not Path(a).is_absolute() else a
                          for a in server.get("args", [])]
        server.setdefault("cwd", str(ROOT))
    return Client(config)


# ---------------------------------------------------------------- the board (shared state)


@dataclass
class Board:
    """What the run puts on the dashboard: events, and everything waiting for a human."""

    run: BoardRun
    run_id: str = ""  # the run currently writing to the board (audit records use it)
    _next_id: int = 1

    def next_id(self) -> int:
        self._next_id += 1
        return self._next_id - 1

    def log(self, ticket_id: int, kind: str, agent: str, text: str, depth: int = 0, to: str | None = None,
            as_run: str | None = None, **audit_fields) -> None:
        """Record a step on the board and append it to the audit trail.

        `as_run` overrides the run id (human actions are logged under the board's id).
        """
        run_id = as_run or self.run_id or self.run.run_id
        self.run.events.append(
            TeamEvent(id=len(self.run.events) + 1, run_id=run_id, ticket_id=ticket_id, kind=kind,
                      agent=agent, to=to, tool=audit_fields.get("tool"), text=text, depth=depth,
                      data={k: audit_fields[k] for k in ("args", "result") if k in audit_fields} or None)
        )
        audit.append(run_id, kind, board_id=self.run.run_id, ticket_id=ticket_id, agent=agent, to=to,
                     depth=depth, text=text, **audit_fields)

    def committed_cash(self) -> float:
        """Cash promised to payment requests still waiting for a human.

        Approved requests are NOT counted: they've been paid, so they're already out of
        the cash_accounts balance. Counting them again would double-count the money.
        """
        return round(sum(p.amount for p in self.run.payment_requests if p.status == "pending"), 2)


@dataclass
class TeamDeps:
    """Passed to every agent run. `chain` is who is waiting on whom right now."""

    board: Board
    agent: AgentName
    chain: tuple[str, ...] = ()
    ticket_id: int = 0
    prerequisite_for: int | None = None  # set when the Boss is solving this ticket for another one

    @property
    def depth(self) -> int:
        return len(self.chain)


# ---------------------------------------------------------------- MCP access per agent


@dataclass
class LoggedToolset(WrapperToolset[TeamDeps]):
    """Wraps the MCP toolset: refuses human-only tools and logs every call to the board."""

    async def call_tool(self, name: str, tool_args: dict[str, Any], ctx: RunContext[TeamDeps], tool: Any) -> Any:
        deps = ctx.deps
        if name in HUMAN_ONLY_TOOLS:
            deps.board.log(deps.ticket_id, "refused", deps.agent, f"{name} is human-only", deps.depth)
            return {"error": f"{name} can only be triggered by a human approving on the dashboard."}
        if name == "resolve_ticket":
            waiting = [i.id for i in (*deps.board.run.payment_requests, *deps.board.run.drafts,
                                      *deps.board.run.discount_requests)
                       if i.ticket_id == tool_args.get("ticket_id") and i.status == "pending"]
            if waiting:
                deps.board.log(deps.ticket_id, "refused", deps.agent,
                               f"resolve_ticket refused: items {waiting} still need a human", deps.depth)
                return {"error": f"Ticket still has payment requests or drafts {waiting} waiting for human "
                                 "approval; mark it waiting_on_human instead of closing it."}
        result = await super().call_tool(name, tool_args, ctx, tool)
        deps.board.log(
            tool_args.get("ticket_id", deps.ticket_id), "tool_call", deps.agent,
            f"{name}({json.dumps(tool_args)}) -> {json.dumps(result, default=str)[:400]}", deps.depth,
            tool=name, args=tool_args, result=result,
        )
        return result


def _mcp_for(agent_name: str, shop: MCPToolset) -> LoggedToolset:
    allowed = MCP_TOOLS[agent_name] - HUMAN_ONLY_TOOLS
    return LoggedToolset(shop.filtered(lambda ctx, tool_def: tool_def.name in allowed))


# ---------------------------------------------------------------- tools every agent shares


async def delegate(
    ctx: RunContext[TeamDeps],
    to: Teammate,
    ticket_id: int,
    question: str,
    good_answer_looks_like: str,
) -> AgentReport | str:
    """Hand a question to a teammate and get their report back (the delegation passport).

    Args:
        to: The teammate who has the tools to answer.
        ticket_id: The ticket this is for.
        question: The exact question, with every id/sku/size/amount they need.
        good_answer_looks_like: What a complete answer contains.
    """
    deps = ctx.deps
    board = deps.board
    chain = deps.chain + (deps.agent,)
    used = board.run.delegations.get(ticket_id, 0)
    refusal = None
    if to == deps.agent:
        refusal = "Refused: you can't delegate to yourself."
    elif to in chain:
        refusal = (f"Refused (no ping-pong): {DISPLAY[to]} is already waiting on this request chain. "
                   "Put what you know in your own report instead.")
    elif len(chain) > MAX_DEPTH:
        refusal = f"Refused: delegation chain is at the limit of {MAX_DEPTH}. Report what you have."
    elif used >= MAX_DELEGATIONS_PER_TICKET:
        refusal = f"Refused: ticket #{ticket_id} has used all {MAX_DELEGATIONS_PER_TICKET} delegations. Report what you have."
    if refusal:
        board.log(ticket_id, "refused", deps.agent, f"delegate to {to}: {refusal}", deps.depth, to=to)
        return refusal
    board.run.delegations[ticket_id] = used + 1

    board.log(ticket_id, "delegate", deps.agent, question, deps.depth, to=to)
    prompt = (
        f"Delegation from {DISPLAY[deps.agent]} about ticket #{ticket_id}.\n"
        f"Question: {question}\n"
        f"A good answer looks like: {good_answer_looks_like}\n"
        f"Request chain (don't delegate back to these): {', '.join(DISPLAY[a] for a in chain)}"
    )
    child = replace(deps, agent=to, chain=chain, ticket_id=ticket_id)
    try:
        report = (await _run_agent(child, prompt, ctx.usage, asked_by=deps.agent)).output
    except UsageLimitExceeded:
        raise  # the run's budget is spent: stop the whole run
    except Exception as exc:
        board.log(ticket_id, "error", to, f"{DISPLAY[to]} couldn't finish: {exc}", child.depth, to=deps.agent)
        return f"{DISPLAY[to]} couldn't finish this request ({type(exc).__name__}). Work with what you have."
    board.log(ticket_id, "report", to, report.answer, child.depth, to=deps.agent)
    return report


def _audit_tool(ctx: RunContext[TeamDeps], tool: str, args: dict, result) -> None:
    """Record a team (non-MCP) tool call in the audit trail."""
    deps = ctx.deps
    audit.append(deps.board.run_id or deps.board.run.run_id, "team_tool_call", board_id=deps.board.run.run_id,
                 ticket_id=args.get("ticket_id", deps.ticket_id), agent=deps.agent, depth=deps.depth,
                 tool=tool, args=args, result=result)


def view_board(ctx: RunContext[TeamDeps]) -> dict:
    """What is already on the dashboard: payment requests (with the cash they commit),
    discounts, customer drafts, tool requests and the Boss's decisions per ticket. Check
    this before preparing another payment so cash is never counted twice, and to see
    whether a ticket you depend on has already been worked."""
    run = ctx.deps.board.run
    ctx.deps.board.log(ctx.deps.ticket_id, "tool_call", ctx.deps.agent,
                       f"view_board() -> {len(run.payment_requests)} payment, {len(run.discount_requests)} discount, "
                       f"{len(run.drafts)} draft request(s)", ctx.deps.depth, tool="view_board", args={})
    return {
        "payment_requests": [p.model_dump(include={"id", "ticket_id", "kind", "ref_id", "payee", "amount",
                                                   "ladder_rank", "status", "sku", "size", "qty", "depends_on"})
                             for p in run.payment_requests],
        "discount_requests": [d.model_dump(include={"id", "ticket_id", "customer", "kind", "discount_pct",
                                                    "discounted_price", "qty", "status"})
                              for d in run.discount_requests],
        "decisions": {t: d.model_dump(include={"status", "decision"}) for t, d in run.decisions.items()},
        "cash_committed_to_pending_requests": ctx.deps.board.committed_cash(),
        "note": "Approved requests are already paid and already out of the cash balance; only subtract pending ones.",
        "customer_drafts": [d.model_dump(include={"id", "ticket_id", "to", "subject", "status"}) for d in run.drafts],
        "tool_requests": [t.model_dump(include={"id", "tool_name", "status"}) for t in run.tool_requests],
    }


# ---------------------------------------------------------------- role-specific tools


async def _shop(tool: str, args: dict | None = None):
    """Read a shop fact through the campus-customs MCP server (used by the guards below)."""
    async with mcp_client() as client:
        result = await client.call_tool(tool, args or {}, raise_on_error=False)
    data = result.structured_content or {}
    return data.get("result", data)


RENT_RESERVE_DAYS = 30  # rent due this soon is set aside before any spending on stock (shop rule 26)


async def rent_to_set_aside(board: Board) -> list[dict]:
    """Rent due within RENT_RESERVE_DAYS that has no request on the board yet (Priority Ladder rung 1)."""
    lease_ids = {t["lease_id"] for t in await _shop("list_tickets") if t.get("lease_id")}
    reserve = []
    for lease_id in sorted(lease_ids):
        lease = await _shop("get_lease", {"lease_id": lease_id})
        requested = any(p.kind == "rent" and p.ref_id == lease_id and p.status == "pending"
                        for p in board.run.payment_requests)
        if "error" not in lease and lease["days_until_due"] <= RENT_RESERVE_DAYS and not requested:
            reserve.append({"lease_id": lease_id, "amount": lease["monthly_rent"], "due": lease["next_due"]})
    return reserve


async def available_cash(board: Board, ladder_rank: int = 1) -> float:
    """Checking balance (from MCP) minus cash promised to pending requests on the board, and,
    for stock or discounts (rung 3+), minus rent that is due soon but not requested yet."""
    cash = await _shop("get_cash_balance", {"account": "checking"})
    available = cash["balance"] - board.committed_cash()
    if ladder_rank >= 3:
        available -= sum(r["amount"] for r in await rent_to_set_aside(board))
    return round(available, 2)


async def prepare_payment_request(
    ctx: RunContext[TeamDeps],
    ticket_id: int,
    kind: str,
    ref_id: int | None,
    payee: str,
    amount: float,
    ladder_rank: int,
    reason: str,
    sku: str | None = None,
    size: str | None = None,
    qty: int | None = None,
) -> dict:
    """Put a payment or purchase order on the dashboard for HUMAN APPROVAL. Pays nothing.

    The board checks it against the real balance (minus pending requests), refuses
    duplicates, and links a purchase order to the invoice that must be paid first.

    Args:
        ticket_id: Ticket this payment is for.
        kind: "invoice", "rent" or "purchase_order".
        ref_id: Invoice id ("invoice"), lease id ("rent") or vendor id ("purchase_order").
        payee: Who gets paid.
        amount: Amount in dollars, from a tool result (purchase order: unit_cost x qty).
        ladder_rank: Priority Ladder rung: 1 rent, 2 blocking overdue bill, 3 stock, 4 nice-to-have.
        reason: Why it should be paid now.
        sku, size, qty: For purchase orders only: what to restock.
    """
    board = ctx.deps.board
    problem, depends_on = None, []
    if kind not in ("invoice", "rent", "purchase_order"):
        problem = 'kind must be "invoice", "rent" or "purchase_order".'
    elif ref_id is None:
        problem = "ref_id is required: the invoice id, lease id or (for a purchase order) vendor id."
    elif kind == "purchase_order" and not (sku and size and qty and qty > 0):
        problem = "A purchase order needs sku, size and a positive qty."
    elif amount <= 0:
        problem = "amount must be positive."
    elif not 1 <= ladder_rank <= 4:
        problem = "ladder_rank must be 1-4."
    elif kind != "purchase_order" and any(p.kind == kind and p.ref_id == ref_id and p.status != "rejected"
                                          for p in board.run.payment_requests):
        problem = f"There is already a request for {kind} {ref_id} on the board."

    if not problem and kind == "invoice":
        # File the payment under the ticket that owns the invoice, so it counts towards that ticket.
        owner = next((t for t in await _shop("list_tickets") if t.get("invoice_id") == ref_id), None)
        if owner and owner["id"] != ticket_id:
            ticket_id = owner["id"]

    if not problem and kind == "rent":
        lease = await _shop("get_lease", {"lease_id": ref_id})
        if "error" in lease:
            problem = lease["error"]
        elif payee.strip().lower() != lease["landlord"].lower():
            problem = f"Lease {ref_id}'s landlord is {lease['landlord']}, not {payee}."

    if not problem and kind == "purchase_order":
        # 1. No duplicate restock: a ticket linked to an invoice for this item is already on order.
        ticket = next((t for t in await _shop("list_tickets") if t["id"] == ticket_id), None)
        if ticket and ticket.get("invoice_id") and ticket.get("sku") == sku and ticket.get("size") == size:
            problem = (f"Ticket #{ticket_id} is linked to invoice {ticket['invoice_id']}, which is the restock "
                       f"order for {sku} size {size}. Paying that invoice releases it; ordering it again "
                       "would be a duplicate.")
        # 2. A blocked vendor can only ship once its invoice is paid: link the PO to that payment.
        if not problem:
            vendor = await _shop("check_vendor_can_ship", {"vendor_id": ref_id})
            if "error" in vendor:
                problem = vendor["error"]
            elif payee.strip().lower() != vendor["name"].lower():
                # 3. The vendor id decides who actually gets paid, so it must match the payee named.
                problem = (f"Vendor id {ref_id} is {vendor['name']} ({vendor['specialty']}), not {payee}. Use the "
                           "vendor id Inventory reported for this item (check list_vendors).")
        if not problem:
            for inv in vendor.get("blocked_by_open_invoices", []):
                req = next((p for p in board.run.payment_requests
                            if p.kind == "invoice" and p.ref_id == inv["id"] and p.status != "rejected"), None)
                if req is None:
                    problem = (f"{vendor.get('name')} won't ship while invoice {inv['id']} (${inv['amount']:.2f}) "
                               "is open, and no payment for it is on the board. Get that invoice paid first "
                               "(the Boss can solve the ticket that owns it with solve_ticket_first).")
                    break
                if req.status == "pending":
                    depends_on.append(req.id)

    if not problem:
        available = await available_cash(board, ladder_rank)
        if amount > available:
            held = " and rent due soon that is set aside" if ladder_rank >= 3 else ""
            problem = (f"Not enough cash: {amount:.2f} is more than the {available:.2f} available "
                       f"(checking balance minus requests already waiting for approval{held}).")
            if kind == "purchase_order" and qty:
                fits = int(available // (amount / qty)) if available > 0 else 0
                problem += f" The most that fits is {fits} unit(s)."
    if problem:
        board.log(ticket_id, "refused", ctx.deps.agent, f"payment request refused: {problem}", ctx.deps.depth)
        return {"error": problem}

    request = PaymentRequest(
        id=board.next_id(), ticket_id=ticket_id, kind=kind, ref_id=ref_id, payee=payee, amount=amount,
        balance_before=available, balance_after=round(available - amount, 2), ladder_rank=ladder_rank,
        reason=reason, sku=sku, size=size, qty=qty, depends_on=depends_on,
    )
    board.run.payment_requests.append(request)
    after = f" (after request #{', #'.join(map(str, depends_on))})" if depends_on else ""
    board.log(ticket_id, "payment_request", ctx.deps.agent,
              f"#{request.id} {kind} {payee} ${amount:.2f} (rung {ladder_rank}){after} - waiting for human approval",
              ctx.deps.depth, request=request.model_dump())
    return {"prepared": True, "request_id": request.id, "status": "pending human approval",
            "available_before": available, "available_after_if_approved": request.balance_after,
            "must_be_approved_after": depends_on}


async def prepare_discount_request(
    ctx: RunContext[TeamDeps],
    ticket_id: int,
    customer: str,
    kind: str,
    sku: str,
    qty: int,
    discount_pct: float,
    reason: str,
) -> dict:
    """Put a discount on the dashboard for HUMAN APPROVAL. Nothing is offered until a human approves it.

    Priced from the pricing table (via MCP) and refused if it breaks the Cost Floor
    (price must stay at or above unit_cost / 0.70, i.e. a 30% margin).

    Args:
        ticket_id: Ticket the discount is for.
        customer: Customer name, as on the ticket.
        kind: "this_order" (lower price now) or "future_order" (credit on their next order).
        sku: Product discounted.
        qty: Units it applies to.
        discount_pct: Percent off list price, e.g. 10 for 10%.
        reason: Why the discount is worth it (e.g. "thanks for accepting a split delivery").
    """
    board = ctx.deps.board
    problem = None
    pricing = await _shop("get_pricing", {"sku": sku})
    if kind not in ("this_order", "future_order"):
        problem = 'kind must be "this_order" or "future_order".'
    elif "error" in pricing:
        problem = pricing["error"]
    elif qty <= 0 or not 0 < discount_pct < 100:
        problem = "qty must be positive and discount_pct between 0 and 100."
    elif any(d.ticket_id == ticket_id and d.status == "pending" for d in board.run.discount_requests):
        problem = f"Ticket #{ticket_id} already has a discount waiting for approval."
    if not problem:
        price = round(pricing["list_price"] * (1 - discount_pct / 100), 2)
        floor = pricing["cost_floor_price"]
        if price < floor:
            max_pct = round(100 * (1 - floor / pricing["list_price"]), 1)
            problem = (f"Breaks the Cost Floor: ${price:.2f} is below ${floor:.2f} "
                       f"(the most you can take off {sku} is {max_pct}%).")
    if problem:
        board.log(ticket_id, "refused", ctx.deps.agent, f"discount refused: {problem}", ctx.deps.depth)
        return {"error": problem}

    request = DiscountRequest(
        id=board.next_id(), ticket_id=ticket_id, customer=customer, kind=kind, sku=sku, qty=qty,
        list_price=pricing["list_price"], unit_cost=pricing["unit_cost"], discount_pct=discount_pct,
        discounted_price=price, margin_pct=round(100 * (price - pricing["unit_cost"]) / price, 1),
        floor_price=floor, reason=reason, prepared_by=ctx.deps.agent,
    )
    board.run.discount_requests.append(request)
    when = "on this order" if kind == "this_order" else "on their next order"
    board.log(ticket_id, "discount_request", ctx.deps.agent,
              f"#{request.id} {discount_pct:g}% off {qty} x {sku} {when} for {customer}: ${price:.2f} each "
              f"(margin {request.margin_pct}%) - waiting for human approval",
              ctx.deps.depth, discount=request.model_dump())
    return {"prepared": True, "discount_request_id": request.id, "discounted_price": price,
            "margin_pct": request.margin_pct, "status": "pending human approval - do not promise it yet"}


# Words that give away the shop's books or internal steps (shop rule 17).
INTERNAL_WORDS = re.compile(r"\b(approv\w*|invoice\w*|bills?|paid|payments?|supplier\w*|vendor\w*|cash|"
                            r"balance|margin\w*|unit cost|rent|pending order|purchase order)\b", re.IGNORECASE)


async def draft_customer_message(
    ctx: RunContext[TeamDeps], ticket_id: int, to: str, subject: str, body: str, facts_used: list[Fact]
) -> dict:
    """Put a customer message on the board as a DRAFT for human approval. Never sends it.

    The board refuses a draft that mentions internal matters (approvals, invoices,
    payments, suppliers, cash...), and, when the item isn't on the shelf yet, one
    that doesn't say how many days it will take.

    Args:
        ticket_id: Ticket the message answers.
        to: Customer name, as on the ticket.
        subject: Subject line.
        body: The full message.
        facts_used: Each confirmed fact the message relies on, with its source.
    """
    board = ctx.deps.board
    problem = None
    leaked = sorted({m.group(0).lower() for m in INTERNAL_WORDS.finditer(f"{subject} {body}")})
    if leaked:
        problem = (f"Customers never see internal matters; remove: {', '.join(leaked)}. Say what happens "
                   "and when, e.g. 'ready about 5 days after we release the restock, on or about September 5'.")
    else:
        ticket = next((t for t in await _shop("list_tickets") if t["id"] == ticket_id), None)
        if ticket and ticket.get("sku") and ticket.get("size"):
            stock = await _shop("check_stock", {"sku": ticket["sku"], "size": ticket["size"],
                                                "qty_needed": ticket.get("qty") or 1})
            if stock.get("shortfall", 0) > 0 and not re.search(r"\bdays?\b", body, re.IGNORECASE):
                problem = ("Part of this order isn't on the shelf yet: say how many days after we release the "
                           "restock it will be ready (the vendor's lead_days), as well as the date.")
    if problem:
        board.log(ticket_id, "refused", ctx.deps.agent, f"draft refused: {problem}", ctx.deps.depth)
        return {"error": problem}
    draft = CustomerDraft(id=board.next_id(), ticket_id=ticket_id, to=to, subject=subject, body=body,
                          facts_used=facts_used)
    board.run.drafts.append(draft)
    board.log(ticket_id, "draft", ctx.deps.agent, f"draft #{draft.id} to {to}: {subject}", ctx.deps.depth,
              draft=draft.model_dump())
    return {"drafted": True, "draft_id": draft.id, "status": "on the board, waiting for human approval"}


def request_new_tool(
    ctx: RunContext[TeamDeps],
    ticket_id: int,
    tool_name: str,
    what_it_does: str,
    tables: str,
    unlocks: str,
    why_existing_tools_fail: str,
) -> dict:
    """Ask the human to add a missing tool to the MCP server. It is NOT available until
    the human approves it and it is added to the server.

    Args:
        ticket_id: Ticket that is blocked without it.
        tool_name: Clear snake_case name, e.g. "get_lease".
        what_it_does: Inputs and what it returns or changes.
        tables: Tables it reads or writes.
        unlocks: Which ticket(s) it unlocks and how.
        why_existing_tools_fail: Why the current tools can't do this job.
    """
    board = ctx.deps.board
    if any(t.tool_name == tool_name for t in board.run.tool_requests):
        return {"error": f"{tool_name} has already been requested this run."}
    request = ToolRequest(id=board.next_id(), ticket_id=ticket_id, tool_name=tool_name,
                          what_it_does=what_it_does, tables=tables, unlocks=unlocks,
                          why_existing_tools_fail=why_existing_tools_fail)
    board.run.tool_requests.append(request)
    board.log(ticket_id, "tool_request", ctx.deps.agent, f"requested MCP tool {tool_name}: {unlocks}",
              ctx.deps.depth, tool_request=request.model_dump())
    return {"requested": True, "tool_request_id": request.id,
            "status": "waiting for human approval - not available in this run"}


async def _record_decisions(board: Board, plan: BoardPlan, only_ticket: int | None) -> None:
    """Store the Boss's decisions on the board and close any ticket with nothing left for a human."""
    for d in plan.decisions:
        if only_ticket and d.ticket_id != only_ticket:
            continue  # a single-ticket run only decides that ticket
        board.run.decisions[d.ticket_id] = d
        board.log(d.ticket_id, "decision", "boss", f"[{d.status}] {d.decision}", decision=d.model_dump())
        await resolve_if_done(board, d.ticket_id)


async def solve_ticket_first(ctx: RunContext[TeamDeps], ticket_id: int, why: str) -> dict:
    """Work another open ticket FIRST, because the current ticket depends on it.

    Example: a restock you need is blocked by an unpaid invoice that belongs to another
    open ticket. That ticket's payment has to be requested (and approved) before your
    purchase order can be paid. Runs the full team on that ticket and returns the Boss's
    decision for it. Only one level deep; it won't re-run a ticket already decided.

    Args:
        ticket_id: The ticket to solve first.
        why: The dependency, e.g. "#103's restock vendor is blocked by invoice 501, owned by #101".
    """
    deps = ctx.deps
    board = deps.board
    current = deps.ticket_id
    if deps.prerequisite_for is not None:
        return {"error": "Already solving a prerequisite; finish this ticket first (one level only)."}
    if ticket_id == current:
        return {"error": "That's the ticket you're already working on."}
    ticket = next((t for t in await _shop("list_tickets") if t["id"] == ticket_id), None)
    if ticket is None:
        return {"error": f"No ticket {ticket_id}."}
    if ticket["status"] == "resolved":
        return {"ticket_id": ticket_id, "status": "already resolved", "notes": ticket["notes"]}
    earlier = board.run.decisions.get(ticket_id)
    if earlier and earlier.status != "blocked":
        return {"ticket_id": ticket_id, "status": f"already worked: {earlier.status}",
                "decision": earlier.decision, "summary": earlier.summary}

    board.log(current, "dependency", "boss", f"#{current} depends on #{ticket_id}: {why}. Solving #{ticket_id} first.",
              deps.depth, depends_on=ticket_id)
    child = TeamDeps(board=board, agent="boss", ticket_id=ticket_id, prerequisite_for=current)
    prompt = ticket_prompt(ticket_id) + (
        f" You are solving it first because ticket #{current} depends on it: {why}. "
        f"Don't work ticket #{current} yourself; just settle #{ticket_id}.")
    result = await _run_agent(child, prompt, asked_by="boss")  # its own per-ticket budget
    used = result.usage
    audit.append(board.run_id, "prerequisite_end", board_id=board.run.run_id, ticket_id=ticket_id,
                 for_ticket=current, model_requests=used.requests, input_tokens=used.input_tokens,
                 output_tokens=used.output_tokens)
    board.run.model_requests += used.requests
    await _record_decisions(board, result.output, ticket_id)
    decision = board.run.decisions.get(ticket_id)
    board.log(current, "dependency", "boss", f"Back on #{current}: #{ticket_id} is "
              f"{decision.status if decision else 'undecided'}.", deps.depth, depends_on=ticket_id)
    return {"ticket_id": ticket_id, "status": decision.status if decision else "no decision",
            "decision": decision.decision if decision else None,
            "summary": decision.summary if decision else None,
            "board": "See view_board for the payment requests it put on the board."}


# ---------------------------------------------------------------- the team


def _audited(fn):
    """Wrap a team tool so each call (args and result, refusals too) goes to the audit trail."""
    import functools, inspect

    @functools.wraps(fn)
    async def wrapper(ctx, *args, **kwargs):
        bound = inspect.signature(fn).bind(ctx, *args, **kwargs)
        call_args = {k: v for k, v in bound.arguments.items() if k != "ctx"}
        call_args = {k: (v.model_dump() if hasattr(v, "model_dump") else
                         [x.model_dump() if hasattr(x, "model_dump") else x for x in v] if isinstance(v, list) else v)
                     for k, v in call_args.items()}
        result = fn(ctx, *args, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        _audit_tool(ctx, fn.__name__, call_args,
                    result.model_dump() if hasattr(result, "model_dump") else result)
        return result
    return wrapper


prepare_payment_request = _audited(prepare_payment_request)
prepare_discount_request = _audited(prepare_discount_request)
draft_customer_message = _audited(draft_customer_message)
request_new_tool = _audited(request_new_tool)
solve_ticket_first = _audited(solve_ticket_first)
delegate = _audited(delegate)


ROLE_TOOLS = {
    "boss": [delegate, view_board, request_new_tool, solve_ticket_first],
    "inventory": [delegate, view_board],
    "accounting": [delegate, view_board, prepare_payment_request, prepare_discount_request],
    "facilities": [delegate, view_board],
    "customer_service": [delegate, view_board, draft_customer_message],
}
OUTPUT_TYPES = {"boss": BoardPlan}  # everyone else reports back with an AgentReport

SHOP = MCPToolset(mcp_client())
_model = build_model()

AGENTS: dict[str, Agent[TeamDeps, Any]] = {
    name: Agent(
        _model,
        name=name,
        deps_type=TeamDeps,
        output_type=OUTPUT_TYPES.get(name, AgentReport),
        instructions=instructions_for(name),
        tools=tools,
        toolsets=[_mcp_for(name, SHOP)],
        model_settings=OpenAIResponsesModelSettings(max_tokens=MAX_TOKENS_PER_REPLY,
                                                    openai_reasoning_effort=REASONING_EFFORT.get(name, "low"),
                                                    parallel_tool_calls=False),  # one step at a time, in order
        retries=2,
    )
    for name, tools in ROLE_TOOLS.items()
}


@AGENTS["boss"].output_validator
async def check_boss_plan(ctx: RunContext[TeamDeps], plan: BoardPlan) -> BoardPlan:
    """Send the Boss back to work if a customer ticket's decision skips a required step."""
    board = ctx.deps.board
    tickets = {t["id"]: t for t in await _shop("list_tickets")}
    for d in plan.decisions:
        t = tickets.get(d.ticket_id)
        if not t or not t.get("sku") or d.status == "blocked":
            continue
        checked = any(e.kind == "tool_call" and e.tool == "check_stock" and e.ticket_id == d.ticket_id
                      for e in board.run.events)
        if not checked:
            raise ModelRetry(f"Ticket #{d.ticket_id} is a customer order: delegate to Inventory to check stock for "
                             f"{t['sku']} size {t['size']} (qty {t['qty']}) before deciding.")
        if t.get("invoice_id"):
            continue  # the ticket's own invoice is the restock (e.g. #101), so it is filled in full
        stock = await _shop("check_stock", {"sku": t["sku"], "size": t["size"], "qty_needed": t["qty"]})
        ordered = sum(p.qty or 0 for p in board.run.payment_requests
                      if p.ticket_id == d.ticket_id and p.kind == "purchase_order" and p.status != "rejected")
        promised = stock.get("qty", 0) + ordered
        has_discount = any(x.ticket_id == d.ticket_id and x.status != "rejected" for x in board.run.discount_requests)
        if promised < t["qty"] and not has_discount and "no goodwill discount because" not in d.reasoning.lower():
            raise ModelRetry(
                f"Ticket #{d.ticket_id}: {t['requester']} gets {promised} of {t['qty']} now or on the restock, so "
                f"they must wait for the rest. Make the goodwill offer: delegate to Accounting to prepare a discount "
                f"request (within the Cost Floor) and to Customer Service to include it in the message. If you "
                f"truly shouldn't, write 'No goodwill discount because ...' in your reasoning.")
    return plan


BOARD_PROMPT = (
    "Work the Campus Customs board. Read every open ticket, delegate the work to your team, "
    "and return one decision per ticket plus the cash plan across all of them."
)


async def _run_agent(deps: TeamDeps, prompt: str, usage=None, asked_by: str | None = None):
    """Run one agent and append an `agent_run` record to the audit trail.

    Delegated runs pass the caller's `usage`, so every agent counts against the same limits.
    """
    board = deps.board
    record = dict(agent=deps.agent, ticket_id=deps.ticket_id, asked_by=asked_by, depth=deps.depth,
                  chain=list(deps.chain), prompt=prompt)
    try:
        result = await AGENTS[deps.agent].run(prompt, deps=deps, usage=usage, usage_limits=LIMITS)
    except Exception as exc:
        audit.append(board.run_id, "agent_run", **record, stop_reason=type(exc).__name__, error=str(exc))
        raise
    run_usage = result.usage
    audit.append(board.run_id, "agent_run", **record, stop_reason="completed",
                 output=result.output.model_dump(),
                 usage_so_far={"requests": run_usage.requests, "input_tokens": run_usage.input_tokens,
                               "output_tokens": run_usage.output_tokens})
    return result


def ticket_prompt(ticket_id: int) -> str:
    return (
        f"Work ticket #{ticket_id} only. Read it from the board with list_open_tickets. Earlier runs may "
        "already have put payment requests or drafts on the board for other tickets: check view_board and "
        f"count that cash as committed. Return one decision for ticket #{ticket_id} and the cash plan."
    )


def new_board() -> Board:
    """A fresh, empty board (one per database reset)."""
    return Board(BoardRun(run_id=uuid.uuid4().hex[:8]))


async def run_team(board: Board | None = None, ticket_id: int | None = None) -> BoardRun:
    """One run of the agent team: on one ticket, or on the whole open board if ticket_id is None.

    Results are added to `board`, so later runs see what earlier runs left for the human.
    """
    board = board or new_board()
    board.run_id = uuid.uuid4().hex[:8]
    board.run.current_run = board.run_id
    board.run.delegations = {}  # delegation limits are per run
    prompt = ticket_prompt(ticket_id) if ticket_id else BOARD_PROMPT
    focus = ticket_id or 0
    deps = TeamDeps(board=board, agent="boss", ticket_id=focus)
    audit.append(board.run_id, "run_start", board_id=board.run.run_id, ticket_id=ticket_id, model=MODEL_NAME,
                 prompt=prompt,
                 limits={"max_depth": MAX_DEPTH, "max_delegations_per_ticket": MAX_DELEGATIONS_PER_TICKET,
                         "request_limit": REQUEST_LIMIT, "tool_calls_limit": TOOL_CALLS_LIMIT,
                         "total_tokens_limit": TOTAL_TOKENS_LIMIT, "max_tokens_per_reply": MAX_TOKENS_PER_REPLY,
                         "reasoning_effort": {n: REASONING_EFFORT.get(n, "low") for n in AGENTS}},
                 mcp_tools={k: sorted(v) for k, v in MCP_TOOLS.items()})
    board.log(focus, "start", "boss", f"Boss picks up ticket #{ticket_id}" if ticket_id else "Boss picks up the board")
    usage = None
    async with SHOP:  # one MCP server process for the whole run
        try:
            result = await _run_agent(deps, prompt)
            board.run.plan = result.output
            board.run.stop_reason = "completed"
            usage = result.usage
        except UsageLimitExceeded as exc:
            board.log(focus, "error", "boss", f"stopped by a usage limit: {exc}")
            board.run.stop_reason = "usage_limit"
        except Exception as exc:
            board.log(focus, "error", "boss", f"stopped by an error: {exc}")
            board.run.stop_reason = "error"
    if board.run.plan and board.run.stop_reason == "completed":
        await _record_decisions(board, board.run.plan, ticket_id)
    requests = usage.requests if usage else 0
    board.run.model_requests += requests
    board.log(focus, "end", "boss", f"run finished: {board.run.stop_reason}")
    audit.append(board.run_id, "run_end", board_id=board.run.run_id, ticket_id=ticket_id,
                 stop_reason=board.run.stop_reason, model_requests=requests,
                 input_tokens=usage.input_tokens if usage else None,
                 output_tokens=usage.output_tokens if usage else None,
                 payment_requests=len(board.run.payment_requests), drafts=len(board.run.drafts),
                 tool_requests=len(board.run.tool_requests))
    board.run.current_run = None
    return board.run


async def run_board(prompt: str = BOARD_PROMPT) -> BoardRun:
    """One full run of the agent team over the whole open board, on a fresh board."""
    return await run_team(new_board())


async def resolve_if_done(board: Board, ticket_id: int, approved_by: str | None = None) -> bool:
    """Mark a ticket resolved (via MCP resolve_ticket) once its run is finished and nothing is left
    for a human: the Boss has decided, the ticket isn't blocked, and every payment request AND
    every customer draft for it has been approved. Anything pending keeps it open; anything
    rejected keeps it open too, so the team can try again.
    """
    decision = board.run.decisions.get(ticket_id)
    requests = [p for p in board.run.payment_requests if p.ticket_id == ticket_id]
    drafts = [d for d in board.run.drafts if d.ticket_id == ticket_id]
    discounts = [d for d in board.run.discount_requests if d.ticket_id == ticket_id]
    if (decision is None or decision.status == "blocked"
            or any(item.status != "approved" for item in (*requests, *drafts, *discounts))):
        return False
    paid = "; ".join(f"{p.kind} ${p.amount:.2f} to {p.payee} approved by {p.approved_by}" for p in requests)
    signed = "; ".join(f"message to {d.to} approved by {d.approved_by} (not sent)" for d in drafts)
    offered = "; ".join(f"{d.discount_pct:g}% off {d.qty} x {d.sku} ({d.kind.replace('_', ' ')}) approved by "
                        f"{d.approved_by}" for d in discounts)
    reason = (f"{decision.decision} {decision.summary}" + (f" Payments: {paid}." if paid else "")
              + (f" Discounts: {offered}." if offered else "")
              + (f" Customer drafts: {signed}." if signed else ""))
    async with mcp_client() as client:
        result = await client.call_tool("resolve_ticket", {"ticket_id": ticket_id, "reason": reason,
                                                           "resolved_by": "Boss"}, raise_on_error=False)
    data = result.structured_content or {}
    if data.get("error") and "already resolved" not in data["error"]:
        board.log(ticket_id, "error", "boss", f"couldn't resolve ticket: {data['error']}", as_run=board.run.run_id)
        return False
    decision.status = "resolved"
    board.log(ticket_id, "resolved", "boss", f"Ticket #{ticket_id} marked resolved. {decision.summary}",
              as_run=board.run.run_id, reason=reason, approved_by=approved_by)
    return True


# ---------------------------------------------------------------- human approval (dashboard)


async def approve_payment(board: Board, request_id: int, approved_by: str) -> PaymentRequest:
    """A human approved a payment request: only now is make_payment called, over MCP.

    If make_payment refuses (e.g. not enough cash, or the vendor is still blocked),
    the request stays pending and the refusal is in `request.result`.
    """
    request = next(p for p in board.run.payment_requests if p.id == request_id)
    if request.status != "pending":
        raise ValueError(f"Payment request {request_id} is already {request.status}.")
    first = [p for p in board.run.payment_requests if p.id in request.depends_on and p.status != "approved"]
    if first:
        names = ", ".join(f"#{p.id} ({p.kind} ${p.amount:.2f} to {p.payee})" for p in first)
        request.result = {"error": f"Approve {names} first: this order can't ship until then."}
        return request
    args = {"kind": request.kind, "ref_id": request.ref_id, "approved_by": approved_by}
    if request.kind == "purchase_order":
        args.update(sku=request.sku, size=request.size, qty=request.qty)
    async with mcp_client() as client:
        result = await client.call_tool("make_payment", args, raise_on_error=False)
    request.result = result.structured_content
    paid = bool(request.result and request.result.get("paid"))
    if paid:
        request.status, request.approved_by = "approved", approved_by
    outcome = "paid" if paid else f"refused: {(request.result or {}).get('error', 'no result')}"
    board.log(request.ticket_id, "human_action", "boss",
              f"{approved_by} approved request #{request_id} ({request.kind} ${request.amount:.2f}): {outcome}",
              as_run=board.run.run_id, action="approve_payment", item_id=request_id, human=approved_by,
              tool="make_payment", args=args, result=request.result)
    if paid:
        await resolve_if_done(board, request.ticket_id, approved_by)
    return request


async def approve_draft(board: Board, draft_id: int, approved_by: str) -> CustomerDraft:
    """A human approved a customer draft. It is marked approved; it is still never sent."""
    draft = next(d for d in board.run.drafts if d.id == draft_id)
    if draft.status != "pending":
        raise ValueError(f"Draft {draft_id} is already {draft.status}.")
    draft.status, draft.approved_by = "approved", approved_by
    board.log(draft.ticket_id, "human_action", "customer_service",
              f"{approved_by} approved draft #{draft_id} to {draft.to} (not sent)",
              as_run=board.run.run_id, action="approve_draft", item_id=draft_id, human=approved_by)
    await resolve_if_done(board, draft.ticket_id, approved_by)
    return draft


async def approve_discount(board: Board, discount_id: int, approved_by: str) -> DiscountRequest:
    """A human approved a discount. Only now may the customer be told about it."""
    discount = next(d for d in board.run.discount_requests if d.id == discount_id)
    if discount.status != "pending":
        raise ValueError(f"Discount {discount_id} is already {discount.status}.")
    discount.status, discount.approved_by = "approved", approved_by
    board.log(discount.ticket_id, "human_action", "accounting",
              f"{approved_by} approved discount #{discount_id}: {discount.discount_pct:g}% off for {discount.customer}",
              as_run=board.run.run_id, action="approve_discount", item_id=discount_id, human=approved_by)
    await resolve_if_done(board, discount.ticket_id, approved_by)
    return discount


def reject(board: Board, item_id: int, rejected_by: str) -> None:
    """A human rejected a payment request, draft or tool request."""
    for item in (*board.run.payment_requests, *board.run.discount_requests, *board.run.drafts,
                 *board.run.tool_requests):
        if item.id == item_id:
            if item.status != "pending":
                raise ValueError(f"Item {item_id} is already {item.status}.")
            item.status = "rejected"
            board.log(item.ticket_id, "human_action", "boss", f"{rejected_by} rejected item #{item_id}",
                      as_run=board.run.run_id, action="reject", item_id=item_id, human=rejected_by)
            return
    raise KeyError(item_id)


if __name__ == "__main__":
    run = asyncio.run(run_board())
    out = ROOT / "output" / f"team_run_{run.run_id}.json"
    out.write_text(run.model_dump_json(indent=2))
    print(f"{run.stop_reason}: {len(run.events)} events, {run.model_requests} model requests -> {out}")
