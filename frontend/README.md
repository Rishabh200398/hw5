# Campus Customs: Operations Desk (dashboard)

React + Vite + TypeScript dashboard for the Campus Customs agent team.

1. Start the backend from `backend/`: `../.venv/bin/uvicorn main:app --reload --port 8000`
2. Start the dashboard from here: `npm install`, then `npm run dev`
3. Open http://localhost:5173

Pick a ticket and press **Run the team**, watch the agents in **Live from the back office**, and approve or reject payments under **Your approvals**. The checking balance updates after each approved payment. **Reset database** puts the shop back to its original values.

The browser calls the backend directly at `http://localhost:8000` (set `VITE_API_URL` to use a different one); the backend's CORS settings allow `http://localhost:5173`.
