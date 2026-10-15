"""Campus Customs MCP server — the shop's tools for the agent team.

Nine tools. The first three were Problem 3; the other six were added in
Problem 5, after human approval, so the agent team can read the board and the
shop facts it needs (shop rule 18):
  check_stock            — is the item in stock?             (tickets 101, 103)
  check_vendor_can_ship  — can the supplier restock, when?   (tickets 101, 103)
  make_payment           — pay an invoice, rent or a restock (tickets 101, 102, 103)
  list_open_tickets      — read the board                    (all)
  resolve_ticket         — close a ticket with a reason      (all)
  list_vendors           — who supplies what                 (tickets 101, 103)
  get_pricing            — unit cost and list price          (ticket 103)
  get_cash_balance       — what the shop has to spend        (tickets 101, 102, 103)
  get_lease              — rent amount and due date          (ticket 102)
Plus list_tickets (every ticket, open or resolved), added in Problem 7 for the
dashboard's ticket list. No agent is given it.

Every tool reads or writes ../data/campus_customs_new.db (the working copy).
The original ../data/campus_customs.db is never opened here.

Tools only report what is in the database. Anything worked out (shortfall,
days overdue, arrival dates) is plain arithmetic on database values and
"today" is always desk.date_today, never the computer's clock.

Run from this folder (stdio):  python server.py
Run (HTTP):                    python server.py --http
HTTP URL:                      http://127.0.0.1:8001/mcp
"""

from __future__ import annotations

import argparse
import calendar
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB_PATH = Path(os.environ.get("CAMPUS_CUSTOMS_DB", ROOT / "data" / "campus_customs_new.db"))

mcp = FastMCP("campus-customs")


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _today(conn: sqlite3.Connection) -> date:
    return date.fromisoformat(conn.execute("SELECT date_today FROM desk").fetchone()["date_today"])


def _add_one_month(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=year, month=month, day=min(d.day, calendar.monthrange(year, month)[1]))


@mcp.tool
def check_stock(sku: str, size: str, qty_needed: int = 1) -> dict:
    """Stock on hand for one SKU and size, and how many units are missing.

    Args:
        sku: Product SKU, e.g. "CC-TEE-WHITE".
        size: Size, e.g. "S", "M", or "OS" for one-size items.
        qty_needed: Units the ticket asks for (default 1).
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone()
    if row is None:
        return {"error": f"{sku} size {size} is not in the inventory."}
    return {
        **dict(row),
        "qty_needed": qty_needed,
        "shortfall": max(0, qty_needed - row["qty"]),
        "in_stock": row["qty"] >= qty_needed,
    }


@mcp.tool
def check_vendor_can_ship(vendor_id: int) -> dict:
    """Whether a vendor will ship new product today, and when it would arrive.

    A vendor will not ship while it has an open (unpaid) invoice. Arrival is
    desk.date_today + the vendor's lead_days.
    """
    with _connect() as conn:
        vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if vendor is None:
            return {"error": f"No vendor with id {vendor_id}."}
        today = _today(conn)
        open_invoices = conn.execute(
            "SELECT * FROM invoices WHERE vendor_id = ? AND status = 'open' ORDER BY due_date",
            (vendor_id,),
        ).fetchall()
    blocking = []
    for row in open_invoices:
        invoice = dict(row)
        invoice["days_overdue"] = max(0, (today - date.fromisoformat(invoice["due_date"])).days)
        blocking.append(invoice)
    return {
        **dict(vendor),
        "today": today.isoformat(),
        "can_ship": not blocking,
        "blocked_by_open_invoices": blocking,
        "arrival_if_ordered_today": (today + timedelta(days=vendor["lead_days"])).isoformat(),
    }

# ---------------------------------------------------------------- added in Problem 5


@mcp.tool
def list_open_tickets() -> list[dict]:
    """Every ticket on the board that isn't resolved yet, oldest first, with the
    sku/size/qty, lease_id and invoice_id it points to."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tickets WHERE status != 'resolved' ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]


@mcp.tool
def list_tickets() -> list[dict]:
    """Every ticket on the board, open or resolved, oldest first (for the dashboard)."""
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM tickets ORDER BY created_at").fetchall()]


@mcp.tool
def resolve_ticket(ticket_id: int, reason: str, resolved_by: str) -> dict:
    """Close a ticket and write the reason on it. Refuses without a reason.

    Args:
        ticket_id: Ticket to close.
        reason: What was decided and why (appended to the ticket's notes).
        resolved_by: Who made the call (normally "Boss").
    """
    if not reason.strip() or not resolved_by.strip():
        return {"error": "Refused: a ticket can't be closed without a reason and who closed it."}
    with _connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return {"error": f"No ticket with id {ticket_id}."}
        if row["status"] == "resolved":
            return {"error": f"Ticket {ticket_id} is already resolved."}
        entry = f"[{_today(conn).isoformat()} {resolved_by.strip()}] RESOLVED: {reason.strip()}"
        notes = f"{row['notes']}\n{entry}" if row["notes"] else entry
        conn.execute("UPDATE tickets SET status = 'resolved', notes = ? WHERE id = ?", (notes, ticket_id))
        return dict(conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone())


@mcp.tool
def list_vendors() -> list[dict]:
    """Every vendor with its id, specialty and lead time in days."""
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM vendors ORDER BY id").fetchall()]


@mcp.tool
def get_pricing(sku: str) -> dict:
    """Unit cost, list price and margin for a SKU, plus the lowest price allowed by
    the shop's Cost Floor (30% margin: unit_cost / 0.70)."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if row is None:
        return {"error": f"No pricing for {sku}."}
    margin = row["list_price"] - row["unit_cost"]
    return {
        **dict(row),
        "margin_per_unit": round(margin, 2),
        "margin_pct": round(100 * margin / row["list_price"], 1),
        "cost_floor_price": round(row["unit_cost"] / 0.70, 2),
    }


@mcp.tool
def get_cash_balance(account: str = "checking") -> dict:
    """Current balance of a cash account (the shop only has "checking")."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    if row is None:
        return {"error": f"No cash account named {account!r}."}
    return dict(row)


@mcp.tool
def get_lease(lease_id: int) -> dict:
    """One lease: space, landlord, monthly rent, next due date and days until due
    (counted from desk.date_today; negative means overdue)."""
    with _connect() as conn:
        today = _today(conn)
        row = conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()
    if row is None:
        return {"error": f"No lease with id {lease_id}."}
    lease = dict(row)
    lease["today"] = today.isoformat()
    lease["days_until_due"] = (date.fromisoformat(lease["next_due"]) - today).days
    return lease


# ---------------------------------------------------------------- money (human approval only)


@mcp.tool
def make_payment(
    kind: str,
    ref_id: int,
    approved_by: str,
    account: str = "checking",
    sku: str | None = None,
    size: str | None = None,
    qty: int | None = None,
) -> dict:
    """Pay a vendor invoice, a month's rent, or a restock purchase order.
    REQUIRES HUMAN APPROVAL.

    Only call after a human has approved this payment. Refuses if there is no
    approver, the invoice is not open, the vendor is blocked, or there is not
    enough cash (no negative balances). On success, in one transaction: lowers
    the cash balance, records the payment with its approver, and marks the
    invoice paid or moves the lease's next_due forward one month.

    Args:
        kind: "invoice", "rent" or "purchase_order".
        ref_id: Invoice id ("invoice"), lease id ("rent") or vendor id ("purchase_order").
        approved_by: Name of the human who approved this payment.
        account: Cash account to pay from (default "checking").
        sku, size, qty: For "purchase_order" only: what to restock. The amount is
            pricing.unit_cost x qty; stock arrives after the vendor's lead_days.
    """
    if not approved_by.strip():
        return {"error": "Refused: a human approver is required for every payment."}
    if kind not in ("invoice", "rent", "purchase_order"):
        return {"error": 'kind must be "invoice", "rent" or "purchase_order".'}

    with _connect() as conn:
        today = _today(conn)
        if kind == "invoice":
            item = conn.execute("SELECT * FROM invoices WHERE id = ?", (ref_id,)).fetchone()
            if item is None:
                return {"error": f"No invoice with id {ref_id}."}
            if item["status"] != "open":
                return {"error": f"Invoice {ref_id} is {item['status']!r}, not open."}
            amount = item["amount"]
        elif kind == "rent":
            item = conn.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if item is None:
                return {"error": f"No lease with id {ref_id}."}
            amount = item["monthly_rent"]
        else:
            if not sku or not size or not qty or qty <= 0:
                return {"error": "A purchase order needs sku, size and a positive qty."}
            item = conn.execute("SELECT * FROM vendors WHERE id = ?", (ref_id,)).fetchone()
            if item is None:
                return {"error": f"No vendor with id {ref_id}."}
            if conn.execute(
                "SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)
            ).fetchone() is None:
                return {"error": f"{sku} size {size} is not in the inventory."}
            blocking = conn.execute(
                "SELECT id FROM invoices WHERE vendor_id = ? AND status = 'open'", (ref_id,)
            ).fetchall()
            if blocking:
                ids = ", ".join(str(r["id"]) for r in blocking)
                return {"error": f"Refused: {item['name']} won't ship while invoice(s) {ids} are open."}
            price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
            if price is None:
                return {"error": f"No pricing for {sku}."}
            amount = round(price["unit_cost"] * qty, 2)

        cash = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if cash is None:
            return {"error": f"No cash account named {account!r}."}
        if amount > cash["balance"]:
            return {
                "error": "Refused: not enough cash — balances cannot go negative.",
                "amount": amount,
                "balance": cash["balance"],
                "short_by": round(amount - cash["balance"], 2),
            }

        conn.execute(
            "UPDATE cash_accounts SET balance = balance - ?, date = ? WHERE name = ?",
            (amount, today.isoformat(), account),
        )
        payment_id = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (kind, ref_id, amount, account, today.isoformat(), approved_by.strip()),
        ).lastrowid
        result = {"paid": True}
        if kind == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
            result["invoice"] = dict(conn.execute("SELECT * FROM invoices WHERE id = ?", (ref_id,)).fetchone())
        elif kind == "rent":
            next_due = _add_one_month(date.fromisoformat(item["next_due"])).isoformat()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (next_due, ref_id))
            result["lease"] = dict(conn.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone())
        else:
            # Stock isn't on the shelf until it arrives, so inventory is not changed here.
            result["purchase_order"] = {
                "vendor": item["name"], "sku": sku, "size": size, "qty": qty, "amount": amount,
                "expected_arrival": (today + timedelta(days=item["lead_days"])).isoformat(),
            }
        result["payment"] = dict(conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone())
        result["cash"] = dict(conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchone())
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Campus Customs MCP server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve Streamable HTTP on port 8001 (keeps FastAPI free on 8000)",
    )
    args = parser.parse_args()
    if args.http:
        mcp.run(transport="http", host="127.0.0.1", port=8001)
    else:
        mcp.run()
