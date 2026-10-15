"""Typed shapes the agent team passes around and puts on the board.

Agents fill these in; the dashboard shows them; a human approves the ones that
need approval. Nothing here touches the database. Shop facts only come from MCP.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
Teammate = Literal["inventory", "accounting", "facilities", "customer_service", "boss"]
ApprovalStatus = Literal["pending", "approved", "rejected"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- what agents report


class Fact(BaseModel):
    """One claim plus where it came from (shop rule 16: show your receipts)."""

    claim: str = Field(description="One fact, e.g. 'CC-HOOD-NAVY size M: 8 on hand, short 12'.")
    source: str = Field(description="Tool that returned it (e.g. 'check_stock') or teammate who reported it.")


class AgentReport(BaseModel):
    """What a specialist hands back to whoever delegated to it."""

    ticket_id: int
    answer: str = Field(description="Direct answer to the question you were asked.")
    facts: list[Fact] = Field(default_factory=list, description="Every number or date you used, with its source.")
    open_questions: list[str] = Field(default_factory=list, description="Anything you couldn't answer, and why.")


class TicketDecision(BaseModel):
    """The Boss's final call on one ticket."""

    ticket_id: int
    decision: str = Field(description="What the shop will do.")
    summary: str = Field(description="2-3 plain-English sentences for a non-technical manager: what the team "
                                     "checked, what it found and what happens next. No ids or jargon.")
    reasoning: str = Field(description="Why, including Priority Ladder order and cash arithmetic when money is involved.")
    status: Literal["resolved", "waiting_on_human", "blocked"]
    facts: list[Fact] = Field(default_factory=list)


class BoardPlan(BaseModel):
    """The Boss's output for a full run: one decision per open ticket, plus the cash plan across them."""

    decisions: list[TicketDecision]
    cash_plan: str = Field(description="All planned payments in Priority Ladder order with the running balance.")


# ---------------------------------------------------------------- what waits for a human


class PaymentRequest(BaseModel):
    """A payment or purchase order Accounting prepared. Nothing is paid until a human approves it."""

    id: int = 0
    ticket_id: int
    kind: Literal["invoice", "rent", "purchase_order"]
    ref_id: int = Field(description="Invoice id (invoice), lease id (rent) or vendor id (purchase_order).")
    payee: str
    amount: float = Field(gt=0)
    balance_before: float
    balance_after: float
    ladder_rank: int = Field(ge=1, le=4, description="Priority Ladder rung (1 = rent ... 4 = nice-to-have).")
    reason: str
    sku: str | None = Field(None, description="Purchase orders only: SKU to restock.")
    size: str | None = None
    qty: int | None = None
    prepared_by: AgentName = "accounting"
    depends_on: list[int] = Field(default_factory=list,
                                  description="Payment requests that must be approved first (e.g. the invoice "
                                              "that unblocks the vendor of this purchase order).")
    status: ApprovalStatus = "pending"
    approved_by: str | None = None
    result: dict | None = None
    created_at: str = Field(default_factory=_now)


class DiscountRequest(BaseModel):
    """A discount offered to a customer. Nothing is offered until a human approves it."""

    id: int = 0
    ticket_id: int
    customer: str
    kind: Literal["this_order", "future_order"] = Field(
        description="this_order: a lower price on the current order; future_order: a credit on their next order.")
    sku: str
    qty: int = Field(gt=0, description="Units the discount applies to.")
    list_price: float
    unit_cost: float
    discount_pct: float = Field(gt=0, lt=100)
    discounted_price: float
    margin_pct: float
    floor_price: float
    reason: str
    prepared_by: AgentName = "accounting"
    status: ApprovalStatus = "pending"
    approved_by: str | None = None
    created_at: str = Field(default_factory=_now)


class CustomerDraft(BaseModel):
    """A message to a customer. It stays on the board; nothing is ever sent."""

    id: int = 0
    ticket_id: int
    to: str
    subject: str
    body: str
    facts_used: list[Fact] = Field(default_factory=list)
    status: ApprovalStatus = "pending"
    approved_by: str | None = None
    created_at: str = Field(default_factory=_now)


class ToolRequest(BaseModel):
    """The Boss asking the human to add a tool to the MCP server (shop rule 18)."""

    id: int = 0
    ticket_id: int
    tool_name: str
    what_it_does: str
    tables: str = Field(description="Tables it reads or writes.")
    unlocks: str = Field(description="Which ticket(s) it unlocks and how.")
    why_existing_tools_fail: str
    status: ApprovalStatus = "pending"
    created_at: str = Field(default_factory=_now)


# ---------------------------------------------------------------- what the dashboard watches


class TeamEvent(BaseModel):
    """One step of the agent loop, so a human can watch the agents work."""

    at: str = Field(default_factory=_now)
    ticket_id: int
    id: int = 0
    run_id: str = ""
    kind: Literal["start", "delegate", "report", "tool_call", "payment_request", "draft",
                  "tool_request", "decision", "refused", "error", "human_action", "resolved", "end",
                  "discount_request", "dependency"]
    agent: AgentName
    to: AgentName | None = None
    tool: str | None = Field(None, description="MCP tool name, for tool_call events.")
    data: dict | None = Field(None, description="Structured details (tool args and result), for the dashboard.")
    text: str
    depth: int = 0


class BoardRun(BaseModel):
    """The dashboard's board: everything the team's runs have produced since the last reset.

    It persists across runs, so a run on one ticket sees the payment requests and drafts
    earlier runs left for the human (cash is never counted twice).
    """

    run_id: str = Field(description="Id of the board (one per database reset).")
    current_run: str | None = Field(None, description="Id of the run in progress, if any.")
    plan: BoardPlan | None = Field(None, description="The Boss's output from the latest run.")
    decisions: dict[int, TicketDecision] = Field(default_factory=dict, description="Latest decision per ticket.")
    events: list[TeamEvent] = Field(default_factory=list)
    payment_requests: list[PaymentRequest] = Field(default_factory=list)
    discount_requests: list[DiscountRequest] = Field(default_factory=list)
    drafts: list[CustomerDraft] = Field(default_factory=list)
    tool_requests: list[ToolRequest] = Field(default_factory=list)
    delegations: dict[int, int] = Field(default_factory=dict, description="Delegations per ticket.")
    model_requests: int = 0
    stop_reason: str = ""
