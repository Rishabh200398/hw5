"""Builds the run report from real data, so every number matches the shop database.

Reads:
  output/run_snapshot.json   - the dashboard board + events + tickets captured after the run
  output/audit_trail.json    - every run record since the last db_reset (tokens, tool calls)
  data/campus_customs.db     - starting balance (the original, never changed)
  data/campus_customs_new.db - payments and the ending balance (the working copy)

Writes:
  output/desk_tickets.html   - fills each ticket's "Actual" card and the Cash tab
  output/resolved_tickets.json
  output/resolved_board.html - one screenshot per resolved ticket (output/resolved_board_images/)

Run from the project root:  python3 scripts/build_report.py
"""

from __future__ import annotations

import html
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
NAMES = {"boss": "Boss", "inventory": "Inventory", "accounting": "Accounting",
         "facilities": "Facilities", "customer_service": "Customer Service"}
ORDER = list(NAMES)
KIND = {"invoice": "Pay invoice", "rent": "Pay rent", "purchase_order": "Restock order"}
# Tools that put something on the board for a human (shown separately from read-only checks)
TEAM_TOOLS = {"delegate", "view_board", "prepare_payment_request", "prepare_discount_request",
              "draft_customer_message", "request_new_tool", "solve_ticket_first"}

esc = html.escape


def money(x: float) -> str:
    return f"${x:,.2f}"


# ---------------------------------------------------------------- load


def load():
    snap = json.loads((OUT / "run_snapshot.json").read_text())
    recs = [json.loads(line) for line in (OUT / "audit_trail.json").read_text().splitlines() if line.strip()]
    last_reset = max(i for i, r in enumerate(recs) if r["event"] == "db_reset")
    audit = recs[last_reset:]

    def rows(db, sql):
        with sqlite3.connect(ROOT / "data" / db) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql)]

    db = {
        "start_cash": rows("campus_customs.db", "SELECT * FROM cash_accounts WHERE name='checking'")[0],
        "end_cash": rows("campus_customs_new.db", "SELECT * FROM cash_accounts WHERE name='checking'")[0],
        "payments": rows("campus_customs_new.db", "SELECT * FROM payments ORDER BY id"),
        "vendors": {v["id"]: v for v in rows("campus_customs_new.db", "SELECT * FROM vendors")},
        "tickets": {t["id"]: t for t in rows("campus_customs_new.db", "SELECT * FROM tickets")},
        "invoices": rows("campus_customs_new.db", "SELECT * FROM invoices"),
        "leases": rows("campus_customs_new.db", "SELECT * FROM leases"),
    }
    return snap, audit, db


# ---------------------------------------------------------------- per-ticket facts


def ticket_facts(tid: int, snap: dict, audit: list[dict], db: dict) -> dict:
    board, events = snap["board"], snap["events"]
    ev = [e for e in events if e["ticket_id"] == tid]
    runs = [r for r in audit if r["event"] == "run_start" and r.get("ticket_id") == tid]
    run_ids = {r["run_id"] for r in runs}
    ends = [r for r in audit if r["event"] == "run_end" and r.get("run_id") in run_ids]
    prereq = [r for r in audit if r["event"] == "prerequisite_end" and r.get("ticket_id") == tid]

    # tools per agent: MCP calls (tool_call) and team tools (team_tool_call), for this ticket
    tools: dict[str, Counter] = defaultdict(Counter)
    for r in audit:
        if r["event"] in ("tool_call", "team_tool_call") and r.get("ticket_id") == tid and r.get("tool"):
            tools[r["agent"]][r["tool"]] += 1
    delegations = [e for e in ev if e["kind"] == "delegate"]
    reports = [e for e in ev if e["kind"] == "report"]
    refused = [e for e in ev if e["kind"] == "refused"]
    agents = [a for a in ORDER if a in tools or any(e["agent"] == a or e["to"] == a for e in delegations + reports)]

    pays = [p for p in board["payment_requests"] if p["ticket_id"] == tid]
    discounts = [d for d in board["discount_requests"] if d["ticket_id"] == tid]
    drafts = [d for d in board["drafts"] if d["ticket_id"] == tid]
    decision = board["decisions"].get(str(tid))
    approvals = [e for e in ev if e["kind"] == "human_action"]
    resolved = next((e for e in ev if e["kind"] == "resolved"), None)

    # what each payment really did in the database (vendor name from make_payment's result)
    paid = []
    for p in pays:
        res = p.get("result") or {}
        row = res.get("payment") or {}
        actual_payee = p["payee"]
        if p["kind"] == "purchase_order":
            actual_payee = (res.get("purchase_order") or {}).get("vendor") or db["vendors"].get(p["ref_id"], {}).get("name")
        paid.append({**p, "payment_row": row, "actual_payee": actual_payee,
                     "arrival": (res.get("purchase_order") or {}).get("expected_arrival")})

    return {
        "id": tid, "ticket": db["tickets"][tid], "events": ev, "runs": runs, "ends": ends, "prereq": prereq,
        "tools": tools, "delegations": delegations, "reports": reports, "refused": refused, "agents": agents,
        "payments": paid, "discounts": discounts, "drafts": drafts, "decision": decision,
        "approvals": approvals, "resolved": resolved,
    }


def findings(f: dict, db: dict) -> list[tuple[str, str]]:
    """Automatic checks of the run against the expected behaviour (ok / warn / stop, text)."""
    out = []
    t = f["ticket"]
    if t["status"] == "resolved":
        out.append(("ok", "Ticket is resolved in the database, with the reason written in its notes."))
    for p in f["payments"]:
        if p["status"] == "approved":
            out.append(("ok", f"{KIND[p['kind']]} {money(p['amount'])} approved by {p['approved_by']} and recorded "
                              f"in payments (row {p['payment_row'].get('id')})."))
        if p["kind"] == "purchase_order" and p["actual_payee"] != p["payee"]:
            out.append(("stop", f"Vendor mix-up: the request said payee \"{p['payee']}\" but used vendor id "
                                f"{p['ref_id']}, so make_payment paid <b>{esc(p['actual_payee'])}</b> "
                                f"({esc(db['vendors'][p['ref_id']]['specialty'])}). Inventory had reported Bulldog "
                                f"Print Co (vendor 1). The board didn't check the payee against the vendor id."))
    if t.get("invoice_id") and not any(p["kind"] == "purchase_order" for p in f["payments"]):
        out.append(("ok", f"No duplicate order: invoice {t['invoice_id']} was paid as the restock itself."))
    for d in f["drafts"]:
        if re.search(r"\bdays?\b", d["body"]):
            out.append(("ok", f"Message to {esc(d['to'])} says how many days until it is ready."))
    if f["discounts"]:
        d = f["discounts"][0]
        out.append(("ok", f"Goodwill discount: {d['discount_pct']:g}% off {d['qty']} delayed units "
                          f"({money(d['list_price'])} → {money(d['discounted_price'])}, margin {d['margin_pct']}%), "
                          f"approved by {d['approved_by']}."))
    n_ref = len(f["refused"])
    if n_ref:
        out.append(("warn", f"{n_ref} safety stop(s) fired and the agents corrected themselves "
                            "(details in the step list)."))
    return out


# ---------------------------------------------------------------- desk_tickets.html: Actual cards


def actual_card(f: dict, db: dict) -> str:
    t, d = f["ticket"], f["decision"] or {}
    reqs = sum(r.get("model_requests") or 0 for r in f["ends"]) + sum(r.get("model_requests") or 0 for r in f["prereq"])
    tok_in = sum(r.get("input_tokens") or 0 for r in f["ends"])
    tok_out = sum(r.get("output_tokens") or 0 for r in f["ends"])
    started = f["runs"][0]["time"][11:19] if f["runs"] else "?"
    status = "✓ Resolved" if t["status"] == "resolved" else t["status"]

    chips = "".join(f'<span class="chip in">{NAMES[a]}</span>' for a in f["agents"])
    chips += "".join(f'<span class="chip out">{NAMES[a]}</span>' for a in ORDER if a not in f["agents"])

    steps = []
    for e in f["events"]:
        k, who = e["kind"], NAMES.get(e["agent"], e["agent"])
        if k == "delegate":
            steps.append(f'<li><span class="agent">{who} → {NAMES[e["to"]]}:</span> “{esc(e["text"][:260])}”</li>')
        elif k == "report":
            steps.append(f'<li><span class="agent">{who} → {NAMES[e["to"]]} (report):</span> {esc(e["text"][:300])}</li>')
        elif k == "dependency":
            steps.append(f'<li><span class="agent">{who} (dependency):</span> {esc(e["text"])}</li>')
        elif k in ("payment_request", "discount_request", "draft"):
            steps.append(f'<li><span class="agent">{who} put on the board:</span> {esc(e["text"])}</li>')
        elif k == "refused":
            steps.append(f'<li><span class="agent">Safety stop ({who}):</span> {esc(e["text"][:240])}</li>')
        elif k == "human_action":
            steps.append(f'<li class="human"><span class="agent">Human:</span> {esc(e["text"])}</li>')
        elif k == "decision":
            steps.append(f'<li><span class="agent">Boss decided:</span> {esc(e["text"])}</li>')
        elif k == "resolved":
            steps.append(f'<li><span class="agent">Board:</span> ticket marked <b>resolved</b> through MCP '
                         f'<code>resolve_ticket</code>.</li>')

    tool_rows = "".join(
        f"<tr><th>{NAMES[a]}</th><td>"
        + ", ".join(f"<code>{esc(tool)}</code>{f' ×{n}' if n > 1 else ''}" + ("" if tool in TEAM_TOOLS else " <small>(MCP)</small>")
                    for tool, n in sorted(f["tools"][a].items(), key=lambda x: (x[0] in TEAM_TOOLS, x[0])))
        + "</td></tr>"
        for a in ORDER if f["tools"].get(a))

    board_rows = []
    for p in f["payments"]:
        to = p["actual_payee"]
        board_rows.append(f"<tr><td>{KIND[p['kind']]}</td><td>{money(p['amount'])} to {esc(to)}"
                          + (f" · {p['qty']} × {esc(p['sku'])} size {esc(p['size'])}" if p["kind"] == "purchase_order" else "")
                          + f"</td><td>{p['status']} by {esc(p['approved_by'] or '-')}</td></tr>")
    for x in f["discounts"]:
        board_rows.append(f"<tr><td>Discount</td><td>{x['discount_pct']:g}% off {x['qty']} × {esc(x['sku'])} "
                          f"({money(x['list_price'])} → {money(x['discounted_price'])})</td><td>{x['status']} by "
                          f"{esc(x['approved_by'] or '-')}</td></tr>")
    for x in f["drafts"]:
        board_rows.append(f"<tr><td>Message</td><td>to {esc(x['to'])}: “{esc(x['body'])}”</td><td>{x['status']} by "
                          f"{esc(x['approved_by'] or '-')} (never sent)</td></tr>")

    checks = "".join(f'<div class="callout {lvl}">{txt}</div>' for lvl, txt in findings(f, db))
    prereq_note = ""
    if f["prereq"]:
        prereq_note = " (plus a prerequisite run)"

    return f'''<div class="card actual filled">
    <h3>Actual</h3>
    <p class="sub">Real run on <code>gpt-6-luna</code> · started {started} · {reqs} model requests{prereq_note} ·
      {tok_in:,} input / {tok_out:,} output tokens · final status <b>{status}</b></p>
    <h4>Outcome (Boss's summary)</h4>
    <p>{esc(d.get("summary", "-"))}</p>
    <p><b>Decision:</b> {esc(d.get("decision", "-"))}</p>
    <h4>Agents that worked</h4>
    <div class="who">{chips}</div>
    <h4>Who delegated what, step by step</h4>
    <ol class="flow">{"".join(steps)}</ol>
    <h4>Tools each agent used</h4>
    <table>{tool_rows}</table>
    <h4>What went to the human, and what was approved</h4>
    <table><thead><tr><th>Item</th><th>Details</th><th>Status</th></tr></thead>{"".join(board_rows)}</table>
    <h4>Checks against the expected plan</h4>
    {checks}
  </div>'''


# ---------------------------------------------------------------- desk_tickets.html: Cash tab


def cash_tab(facts: dict[int, dict], db: dict) -> tuple[str, dict]:
    start = db["start_cash"]["balance"]
    by_payment_id = {}
    for f in facts.values():
        for p in f["payments"]:
            if p["payment_row"]:
                by_payment_id[p["payment_row"]["id"]] = (f, p)

    rows, running, ledger = [], start, []
    for pay in db["payments"]:
        f, p = by_payment_id.get(pay["id"], (None, None))
        running = round(running - pay["amount"], 2)
        payee = p["actual_payee"] if p else "?"
        why = p["reason"] if p else ""
        tid = f["id"] if f else "?"
        ledger.append({"payment_id": pay["id"], "ticket_id": tid, "kind": pay["kind"], "ref_id": pay["ref_id"],
                       "payee": payee, "amount": pay["amount"], "approved_by": pay["approved_by"],
                       "balance_after": running, "why": why})
        rows.append(f"<tr><td>#{tid}</td><td>{KIND.get(pay['kind'], pay['kind'])}</td><td>{esc(payee)}</td>"
                    f"<td>{esc(why)}</td><td>{esc(pay['approved_by'])}</td>"
                    f"<td class='num neg'>−{money(pay['amount'])}</td><td class='num'>{money(running)}</td></tr>")

    end = db["end_cash"]["balance"]
    matches = abs(running - end) < 0.005
    per_ticket = []
    for tid, f in facts.items():
        spent = sum(p["amount"] for p in f["payments"] if p["status"] == "approved")
        disc = f["discounts"]
        note = ("No cash moved." if not spent else f"{money(spent)} paid out.")
        if disc:
            note += " The approved discount lowers what the customer pays the shop, but no money comes in during this homework, so it has no cash effect."
        when = f["resolved"]["at"][11:19] if f["resolved"] else "-"
        per_ticket.append(f"<tr><td>#{tid} · {esc(f['ticket']['subject'])}</td><td>{when}</td>"
                          f"<td class='num neg'>{'−' + money(spent) if spent else '$0.00'}</td><td>{note}</td></tr>")

    html_out = f'''<div class="card">
    <h2>Cash: itemized</h2>
    <p class="sub">Checking account only. Cash only goes out in this homework: every line is a payment a human approved.</p>
    <table class="ledger">
      <thead><tr><th>Ticket</th><th>What</th><th>Paid to</th><th>Why</th><th>Approved by</th><th class="num">Amount</th><th class="num">Balance</th></tr></thead>
      <tr class="startrow"><td colspan="6"><b>Starting checking balance</b> (after reset, from <code>campus_customs.db</code>, {db["start_cash"]["date"]})</td><td class="num"><b>{money(start)}</b></td></tr>
      {"".join(rows)}
      <tr class="endrow"><td colspan="6"><b>Ending checking balance</b></td><td class="num"><b>{money(running)}</b></td></tr>
    </table>
    <div class="callout {'ok' if matches else 'stop'}"><b>{'✓ Matches the database' if matches else '✗ Does not match'}</b>
      <code>cash_accounts</code> in <code>data/campus_customs_new.db</code> says checking = <b>{money(end)}</b> (as of {db["end_cash"]["date"]}).
      {money(start)} − {" − ".join(money(p["amount"]) for p in db["payments"])} = {money(running)}.</div>
  </div>
  <div class="card">
    <h3>How cash changed per ticket</h3>
    <table><thead><tr><th>Ticket</th><th>Resolved at (UTC)</th><th class="num">Cash change</th><th>Why</th></tr></thead>{"".join(per_ticket)}</table>
  </div>'''
    return html_out, {"start": start, "end_computed": running, "end_in_db": end, "matches": matches, "ledger": ledger}


CSS_EXTRA = """
  .actual.filled { border: 2px solid var(--ok); background: #fff; }
  .ledger td.num, .ledger th.num, td.num, th.num { text-align: right; white-space: nowrap; }
  td.neg { color: var(--stop); }
  .startrow td, .endrow td { background: #f3f6fb; }
  small { color: var(--muted); }
  .pill-resolved { background: var(--ok-bg) !important; color: var(--ok) !important; }
"""


def update_desk(facts, db):
    path = OUT / "desk_tickets.html"
    s = path.read_text()
    if "/* report */" not in s:
        s = s.replace("</style>", "/* report */" + CSS_EXTRA + "</style>", 1)
    for tid, f in facts.items():
        block = f"<!-- ACTUAL:{tid} -->{actual_card(f, db)}<!-- /ACTUAL:{tid} -->"
        if f"<!-- ACTUAL:{tid} -->" in s:
            s = re.sub(rf"<!-- ACTUAL:{tid} -->.*?<!-- /ACTUAL:{tid} -->", lambda m: block, s, flags=re.S)
        else:  # first time: replace the placeholder card inside this ticket's tab
            sec = re.search(rf'(<section class="tab[^"]*" id="t{tid}".*?)(<div class="card actual">.*?</div>)(\s*</section>)', s, re.S)
            s = s[:sec.start(2)] + block + s[sec.end(2):]
    for tid, f in facts.items():  # header pill shows the ticket's real status from the database
        st = f["ticket"]["status"]
        s = re.sub(rf'(<h2>#{tid} · [^<]*)<span class="pill[^"]*">[^<]*</span>',
                   lambda m: m.group(1) + f'<span class="pill pill-{st}">{"✓ resolved" if st == "resolved" else st}</span>', s)
    cash_html, cash = cash_tab(facts, db)
    s = re.sub(r'(<section class="tab" id="cash" role="tabpanel">).*?(</section>)',
               lambda m: m.group(1) + "\n  " + cash_html + "\n" + m.group(2), s, flags=re.S)
    path.write_text(s)
    return cash


# ---------------------------------------------------------------- resolved_tickets.json


def contributions(f: dict) -> dict:
    out = {}
    for a in f["agents"]:
        tools = dict(f["tools"].get(a, {}))
        said = [e["text"] for e in f["reports"] if e["agent"] == a]
        asked = [{"to": NAMES[e["to"]], "question": e["text"]} for e in f["delegations"] if e["agent"] == a]
        put = [e["text"] for e in f["events"] if e["agent"] == a and e["kind"] in ("payment_request", "discount_request", "draft")]
        stops = [e["text"] for e in f["refused"] if e["agent"] == a]
        entry = {"tools_used": tools}
        if asked:
            entry["delegated"] = asked
        if said:
            entry["reported"] = said
        if put:
            entry["put_on_board_for_human"] = put
        if stops:
            entry["safety_stops"] = stops
        if a == "boss" and f["decision"]:
            entry["final_decision"] = f["decision"]["decision"]
        out[NAMES[a]] = entry
    return out


def write_json(facts, db, cash):
    tickets = []
    for tid, f in facts.items():
        d = f["decision"] or {}
        approvals = []
        for p in f["payments"]:
            approvals.append({"type": "payment", "what": f"{KIND[p['kind']]} {money(p['amount'])}",
                              "paid_to": p["actual_payee"], "status": p["status"], "approved_by": p["approved_by"],
                              "payments_row": p["payment_row"].get("id")})
        for x in f["discounts"]:
            approvals.append({"type": "discount", "what": f"{x['discount_pct']:g}% off {x['qty']} x {x['sku']} "
                              f"({money(x['list_price'])} -> {money(x['discounted_price'])})",
                              "status": x["status"], "approved_by": x["approved_by"]})
        for x in f["drafts"]:
            approvals.append({"type": "customer_message", "what": f"message to {x['to']} (never sent)",
                              "body": x["body"], "status": x["status"], "approved_by": x["approved_by"]})
        times = {e["text"]: e["at"] for e in f["approvals"]}
        tickets.append({
            "id": tid,
            "subject": f["ticket"]["subject"],
            "requester": f["ticket"]["requester"],
            "final_status": f["ticket"]["status"],
            "short_outcome": d.get("summary"),
            "decision": d.get("decision"),
            "resolved_at": f["resolved"]["at"] if f["resolved"] else None,
            "agents": contributions(f),
            "human_approvals": approvals,
            "human_actions_log": [{"at": at, "action": txt} for txt, at in times.items()],
            "cash_change": -round(sum(p["amount"] for p in f["payments"] if p["status"] == "approved"), 2),
            "checks": [{"level": lvl, "note": re.sub("<[^>]+>", "", txt)} for lvl, txt in findings(f, db)],
            "runs": [{"run_id": r["run_id"], "started": r["time"]} for r in f["runs"]],
        })
    doc = {
        "description": "Resolved tickets from the real gpt-6-luna run, built from output/run_snapshot.json, "
                       "output/audit_trail.json and data/campus_customs_new.db by scripts/build_report.py.",
        "starting_checking_balance": cash["start"],
        "ending_checking_balance": cash["end_in_db"],
        "ending_matches_cash_accounts": cash["matches"],
        "tickets": tickets,
    }
    (OUT / "resolved_tickets.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------- resolved_board.html


def write_board(facts, cash):
    cards = []
    for tid, f in facts.items():
        d = f["decision"] or {}
        appr = "".join(
            f"<li>{esc(KIND[p['kind']])} {money(p['amount'])} to {esc(p['actual_payee'])}: <b>{p['status']}</b> by {esc(p['approved_by'] or '-')}</li>"
            for p in f["payments"]) + "".join(
            f"<li>Discount {x['discount_pct']:g}% off {x['qty']} × {esc(x['sku'])}: <b>{x['status']}</b> by {esc(x['approved_by'] or '-')}</li>"
            for x in f["discounts"]) + "".join(
            f"<li>Message to {esc(x['to'])}: <b>{x['status']}</b> by {esc(x['approved_by'] or '-')} (never sent)</li>"
            for x in f["drafts"])
        cards.append(f'''<section class="ticket">
  <div class="head"><h2>#{tid} · {esc(f["ticket"]["subject"])}</h2><span class="badge">✓ {esc(f["ticket"]["status"]).title()}</span></div>
  <p class="meta">{esc(f["ticket"]["requester"])} · resolved at {f["resolved"]["at"][11:19] if f["resolved"] else "-"} UTC ·
    agents: {", ".join(NAMES[a] for a in f["agents"])}</p>
  <p>{esc(d.get("summary", ""))}</p>
  <ul>{appr}</ul>
  <a href="resolved_board_images/ticket_{tid}.png"><img src="resolved_board_images/ticket_{tid}.png" alt="Dashboard showing ticket #{tid} resolved"></a>
  <p class="cap">The Operations Desk with #{tid} selected: ticket board (left), the Boss's summary and the live feed (centre), checking balance and approvals history (right).</p>
</section>''')
    page = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus Customs: Resolved Board</title>
<style>
  body {{ margin: 0; font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #1d2433; background: #f4f6fa; }}
  header {{ background: #00366b; color: #fff; padding: 22px 32px; }}
  header h1 {{ margin: 0; font-size: 24px; }} header p {{ margin: 4px 0 0; color: #c9d7ea; }}
  main {{ max-width: 1120px; margin: 0 auto; padding: 24px 32px 48px; }}
  .summary, .ticket {{ background: #fff; border: 1px solid #dfe4ec; border-radius: 12px; padding: 20px 24px; margin-bottom: 22px; }}
  .head {{ display: flex; justify-content: space-between; align-items: center; }}
  h2 {{ margin: 0; color: #00366b; font-size: 20px; }}
  .badge {{ background: #2f7d4f; color: #fff; font-weight: 700; font-size: 13px; padding: 4px 12px; border-radius: 999px; }}
  .meta, .cap {{ color: #5b6475; font-size: 14px; }}
  img {{ width: 100%; border: 1px solid #dfe4ec; border-radius: 8px; margin-top: 8px; }}
  table {{ border-collapse: collapse; }} td, th {{ padding: 4px 12px 4px 0; text-align: left; }}
</style></head><body>
<header><h1>Campus Customs: Resolved Board</h1>
<p>Real run on gpt-6-luna · every ticket resolved after human approval · checking {money(cash["start"])} → {money(cash["end_in_db"])}
{"(matches cash_accounts)" if cash["matches"] else "(MISMATCH)"}</p></header>
<main>
<section class="summary"><h2>The whole board</h2>
<p class="meta">All three tickets resolved; the checking card shows the ending balance and the approvals history lists every human sign-off.</p>
<a href="resolved_board_images/board_all.png"><img src="resolved_board_images/board_all.png" alt="Dashboard with all tickets resolved"></a></section>
{"".join(cards)}
</main></body></html>'''
    (OUT / "resolved_board.html").write_text(page)


def main():
    snap, audit, db = load()
    facts = {tid: ticket_facts(tid, snap, audit, db) for tid in sorted(db["tickets"])}
    cash = update_desk(facts, db)
    write_json(facts, db, cash)
    write_board(facts, cash)
    print(f"cash: {money(cash['start'])} -> {money(cash['end_computed'])} (db {money(cash['end_in_db'])}) "
          f"matches={cash['matches']}")
    for tid, f in facts.items():
        print(f"#{tid}: {f['ticket']['status']}, agents {[NAMES[a] for a in f['agents']]}, "
              f"{len(f['delegations'])} delegations, findings {[lvl for lvl, _ in findings(f, db)]}")


if __name__ == "__main__":
    main()
