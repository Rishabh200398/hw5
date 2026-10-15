# Campus Customs Multi-Agent Operations (HW5)

An agent team that runs the Campus Customs shop's ticket board. Five PydanticAI agents (Boss, Inventory, Accounting, Facilities, Customer Service) work the open tickets using tools from an **MCP server**. A **FastAPI backend** runs the team, and a **React dashboard** lets a human watch the agents and approve every payment, discount and customer message.

- Every agent runs on **`gpt-6-luna` through Portkey** (no other model is allowed or used).
- Shop facts come only from the MCP server, over `data/campus_customs_new.db`.
- No money moves without a human clicking **Approve**.

```
hw5/
├── AI_prompts.md            prompts I typed while building this
├── requirements.txt         Python packages for the MCP server + backend
├── .env.example             copy to .env and add your Portkey key
├── .mcp.json                registers the MCP server (campus-customs) for Claude Code
├── data/
│   ├── campus_customs.db       original database (never changed)
│   └── campus_customs_new.db   working copy the app reads and writes
├── mcp_server/              FastMCP server (server.py) + README
├── backend/                 FastAPI app (main.py), agent team (team.py), models, prompts/
├── frontend/                React + Vite + TypeScript dashboard
├── scripts/build_report.py  builds the run reports from real data
└── output/                  harness, smoke test, desk tickets, design, resolved tickets/board, audit trail
```

## 1. Set up (once)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then put your PORTKEY_API_KEY in .env
cd frontend && npm install && cd ..
```

## 2. Get a clean database

The app only ever writes to the **working copy**. To start fresh, copy the original over it:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

(The dashboard's **Reset database** button does the same thing, and also clears the board.)

## 3. Start the MCP server

The backend starts the MCP server for you (over stdio, using `.mcp.json`), so you don't need a separate terminal for it. To run it on its own, e.g. to try the tools:

```bash
.venv/bin/python mcp_server/server.py          # stdio
.venv/bin/python mcp_server/server.py --http   # http://127.0.0.1:8001/mcp
```

Opening this folder in Claude Code also loads it from `.mcp.json` as `campus-customs`. See `mcp_server/README.md` for the 10 tools.

## 4. Start the FastAPI backend

```bash
cd backend
../.venv/bin/uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs. The routes are listed in `output/harness.md`.

## 5. Start the React board

In a second terminal:

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173**. The page calls the backend at http://localhost:8000 (CORS allows this origin).

## 6. Run all three tickets

1. **Reset the database first:** click **↺ Reset database** on the dashboard (or run the `cp` command in step 2). Checking goes back to **$3,400**.
2. Type your name in **Approving as**.
3. Click **▶ Run the team** on each ticket (#101 tee, #102 rent, #103 hoodies) in any order. If you start with #103, the Boss works #101 first, because #103's supplier is blocked by #101's unpaid invoice.
4. Watch **Live from the back office**, then approve or reject each payment, discount and customer message under **Your approvals**. A ticket turns **✓ Resolved** once everything for it is approved.

Every run is appended to `output/audit_trail.json` (never wiped). After a run, `python3 scripts/build_report.py` rebuilds the report pages from the real data.

## What's in `output/`

| File | What it is |
|---|---|
| `harness.md` | Tables, MCP tools, the five agents, API routes, dashboard, safety rules, limits |
| `mcp_smoke.json` | Smoke test of the MCP tools against the database |
| `desk_tickets.html` | Per ticket Expected vs Actual, the itemized Cash tab, and the Reflection |
| `design.md` | How the dashboard is designed |
| `resolved_tickets.json` | Each ticket's final status, outcome, agent contributions and human approvals |
| `resolved_board.html` | Dashboard screenshots of each resolved ticket |
| `audit_trail.json` | Append-only log of every run (JSON Lines) |
| `github_url.txt` | This repo's URL |

## Safety in one line

Agents can only *prepare* payments, discounts and messages. A human approves each one on the dashboard. The pay tool refuses negative balances, duplicates, wrong payees and out-of-order orders, and nothing is ever emailed or sent.
