# Campus Customs MCP Server

The shop's toolbox for the Campus Customs agent team. The agents (Boss, Inventory, Accounting, Facilities, Customer Service) call these tools to look up stock and suppliers and to pay bills while resolving the tickets on the board. Built with [FastMCP](https://gofastmcp.com).

## Database

Uses the working copy **`data/campus_customs_new.db`**. The original `data/campus_customs.db` is never opened, so you can reset the working copy from it at any time:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

Tools only return what's in the database (plus simple arithmetic on it). "Today" is always `desk.date_today`, never the computer's clock.

## Tools

Tools 1–3 were built in Problem 3. Tools 4–9 were added in Problem 5, after human approval, so the agent team can read the board and the shop facts it needs. Tool 10 was added in Problem 7 for the dashboard.

| # | Tool | What it does | Tables | Used by | Tickets |
|---|---|---|---|---|---|
| 1 | `check_stock(sku, size, qty_needed=1)` | Stock for one SKU and size, and how many are missing | `inventory` | Inventory | #101, #103 |
| 2 | `check_vendor_can_ship(vendor_id)` | Whether an open unpaid invoice blocks the vendor, and the arrival date (today + lead days) | `vendors`, `invoices`, `desk` | Inventory, Accounting | #101, #103 |
| 3 | `make_payment(kind, ref_id, approved_by, …)` | Pays an invoice, a month's rent or a restock purchase order. **Needs a human approver**, refuses anything the balance can't cover, refuses purchase orders to blocked vendors | reads `invoices`/`leases`/`vendors`/`pricing`/`inventory`/`cash_accounts`/`desk`; writes `cash_accounts`, `payments`, `invoices`/`leases` | **Human only** (dashboard) | #101, #102, #103 |
| 4 | `list_open_tickets()` | Every ticket not yet resolved | `tickets` | Boss | all |
| 5 | `resolve_ticket(ticket_id, reason, resolved_by)` | Closes a ticket and writes the reason on it; refuses without a reason | `tickets` (writes `status`, `notes`) | Boss | all |
| 6 | `list_vendors()` | Vendor ids, specialties and lead days | `vendors` | Inventory | #101, #103 |
| 7 | `get_pricing(sku)` | Unit cost, list price, margin and the 30% cost-floor price | `pricing` | Accounting | #103 |
| 8 | `get_cash_balance(account="checking")` | The current balance | `cash_accounts` | Accounting | #101, #102, #103 |
| 9 | `get_lease(lease_id)` | Rent, landlord, next due date and days until due | `leases`, `desk` | Facilities, Accounting | #102, #103 |
| 10 | `list_tickets()` | Every ticket, open or resolved | `tickets` | Backend only (`GET /api/tickets`) | all |

`make_payment` is never given to an agent: the backend filters it out of their tools and only calls it when a human approves a payment on the dashboard.

See `output/harness.md` for the columns each tool reads and why each one is needed.

## Run

From the project root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Then from this folder:

```bash
../.venv/bin/python server.py
```

That serves over stdio. Add `--http` to serve at http://127.0.0.1:8001/mcp instead.

## Connect to the vibe coder

`.mcp.json` at the project root registers this server as `campus-customs`. Claude Code picks it up when you open the project folder (approve the server when asked).
