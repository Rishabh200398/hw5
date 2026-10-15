# AI Prompts Log

The prompts I typed into the vibe coder while working on this assignment, one section per problem.

---

## Project Overview / Setup

**Prompt:**
> We will be now working on hw 5. The zip folder is called data-hw5 in downloads. Make a folder similar to how we approached the last hw together and unzip the folder there

**Follow-up prompt:**
> its not classowrk. Its a hw. So make a seperate folder

**What was lacking after the first prompt:** The AI created the project folder inside my `AI Classwork 09-29` folder, so I had to ask it to move the project out to its own homework folder (`AI-Assignement 5`), matching my earlier assignments. It then unzipped `data/campus_customs.db`, made the working copy `data/campus_customs_new.db`, and copied over `.gitignore` and `.env` from HW4, with `gpt-6-luna` set as the only model in `.env.example`.

---

## AI Prompts Log

**Prompt:**
> As before I need AI_Prompts.md file. You know what this file means right and what it needs to contain?

---

## Understand the Database and the Open Tickets

**Prompt:**
> I want to now look at data/campus_customs.db and look at every table and its fields. Make it easy for me so show it in a way that is easy to read., Then copy the original file to data/campus_customer_new.db. We will be working on this working copy later. I want to study the 3 open tickets so i can see how they link to other tables.

**Note:** The working copy was named `data/campus_customs_new.db` (the name the assignment requires), not `campus_customer_new.db`.

---

## Start the Harness (output/harness.md)

**Prompt:**
> Okay  thats is helpful. Now i need to create output/harness.md. Here I want to log each table, the list of fields and one short line on why that table matters to the agents. I believe the table desk is valuable as it is like a calender on the wall for the agents to look at the timeline. The tickets are available as it shows the to-do list to agents. The invesntory is useful because it shows the agent when we are in or out of stiock for various things we sell. The pricing is important as the agents will know only then what each item costs the shop and also know how much revenue will the shop be getting by selloing the items. the vendors are importatn as the agents will know who are the suppliers the agents can reach out to to stock the items. and how many days it will take to stock up. The invoices are important as the agent will nderstand teh bills taht the shop owes to suppiers, the leases indicate the shops rent so important to calculate the expenses. The cash account is like the account balance for the agent.  and payment reciept is like a screenshot of the expenses that agents will be making. Refine where ever i have gone wrong

**What the AI refined:** Pricing is about margin (how much discount the shop can afford), not revenue, since revenue isn't modeled. Agents plan restocks with vendors but never contact real ones. Invoices also block shipping: a vendor won't ship while it has an open invoice. The payments table is a permanent record of approved payments (including who approved), not a screenshot.

---

## Problem 3: MCP Server (FastMCP)

**Prompt:**
> Now onto problem 3. Write a mcp server in mcp_server/ using FasMCP. It will talk to data/campus_customs_new.db. We do not need to connect or tun it in this problem. I also want to know which tools do you think the agents will use in this mcp server for solving the tickets in teh database. Keep the names clear and never invent any data, only use info in the db

**What happened:** Created `mcp_server/mcp_server.py` with 19 tools (read tools for tickets, stock, pricing, vendors, invoices, lease and cash; ticket note/resolve tools; and `pay_invoice` / `pay_rent`, which need a human approver and refuse negative balances). The system-wide FastMCP install was broken, so the AI made a project `.venv` and `mcp_server/requirements.txt`. It tested every tool on a throwaway copy of the database, so the working copy stayed untouched, and added the tool list to `output/harness.md`.

**Follow-up prompt:**
> I asked you to write 3 tools that you think will need for the tickts in teh database. did you do that?

**What was lacking:** My original prompt didn't say the number 3, so the AI wrote 19 tools instead of the 3 that problem 3 asks for. I chose to cut the server down to the 3 tools the tickets depend on most: `check_stock` (101, 103), `check_vendor_can_ship` (101, 103) and `make_payment` (101, 102; merges invoice and rent payment, needs a human approver, refuses negative balances). The AI re-tested them on a throwaway database copy and updated `output/harness.md`.

**Prompt:**
> working on the same problem 3, now list each of three mcp tools in output/harness.md, which i believe is already done. But for every tool include, which table it reads, which ticket it helps unlock and one sentence on why that tool it the right one. Do not include vague lines as that will lead to scoring less in my assingment. I need strong argument on wjhy the tool is needed

**What happened:** For each of the 3 tools, `output/harness.md` now lists the tables (and columns) it reads and writes, which agent uses it, the tickets it unlocks with the actual database values (e.g. tee S = 0, invoice 501 is $840 and 3 days overdue, arrival 2026-09-05), and a specific argument for why that tool is needed.

**Prompt:**
> Also add a short mcp_server/Readme.md file that explains what the mcp server is for, which databse file it uses and the three tool it has

---

## Problem 4: Connect the MCP Server to the Vibe Coder

**Prompt:**
> Now onto problem 4. Add MCP server to this project so that the vibe code can call the tools. Save the connnection json text in .mcp.json at the project root

**What happened:** Created `.mcp.json` at the project root. It registers the `campus-customs` server, launched with the project's `.venv` Python and absolute paths, the same way as the class project. The AI tested it by starting the server from `.mcp.json` over stdio: all 3 tools listed, and `check_stock` and `check_vendor_can_ship` returned real database values. The working database was unchanged.

**Follow-up prompt:**
> how do i do that?

**What happened:** The AI moved the vibe-coder session into the `AI-Assignement 5` folder so it could load `.mcp.json`.

**Follow-up prompt:**
> i want ot test other tools too like how you gave me an example now

**Prompt:**
> Okay run these tests and save the evidence i output/mcp_smoke.json. For every tool include the prompt that was asked, the tool name and tool output. It much matc the values in data/campus_customers_new.db

**What happened:** The AI called all 3 tools through the connected `campus-customs` MCP server, 12 calls in total. That covered stock checks (tee S = 0, hoodie M = 8 of 20, cap = 40, plus an XXL size that doesn't exist), vendor checks (vendor 1 blocked by invoice 501, vendor 2 free), and payments (no approver refused, invoice 501 paid, paying it twice refused, rent paid, a second rent payment refused with only $160 left). `output/mcp_smoke.json` records each prompt, tool name, arguments and exact output, plus an SQL query against the database proving the values match. The working copy was reset to the original afterwards. (The database is `campus_customs_new.db`, not `campus_customers_new.db`.)

---

## Problem 5: Agent Team (PydanticAI): Prompts in My Own Words

**Prompt:**
> now onto problem 5. I want to build the agentic team for campus customs using pydanticAI : Bosss, Inventory, Accounting, Facilities and Customer Service. I would want to include prompts, models and agent loop so that they can delegate teh work to each other successfully. The prompt will be as follows. 
> 1) Boss: think of them as the shop manager. Give them a good motto. Their mission should be to make the correct judgement call on how they ensure that they have enough to order the q2 extra hoodies. They need to do this by effectively delegating the work as mentioned on the ticket to their team. The boss will never pay anything itself or close a ticket without reason. 
>
> 2) Inventory: Give them a good motto. Mission is to check the stock per size, works out the shortfall and finds the right vendor and checks wither that vendor is blocked or not. The tools they use is check_stock, check_vendor_can_ship. It delegates the work to accounting whenever the vendor is blocked by an unpaid invoice. Never promise arrival date that tool did not calcualte. Include anythign that I might have missed in this prompt
>
> 3)Accoybtibg: give them a motto. They safeguard the account balance. They should be able to subtract, add money into the account balance. They only prpear payment for human approval. They never make the pay,ment without the apporval of human from teh dashboard. Never provide dicount below the cost. Add anyting i would have missed. Never inflate more money that you actuyally have
>
> 4)Facilities: Create a motto, mission for them. The basic idea is to ensure that they check hwo much rent is owned and when and flags teh consqueneces of paying late. Include some checks in it like never let rent slip quietly. Add nything i would have missed
>
> 5) Customer service. Give them some good motto and mission. They draft beuautify messages to customers. Provide prmpts on what and when it delegates things to accounting and inventroy. Never sends the mnessages directly to customers. Those need to be approved. Never makes false prmoises to people, never gives out internal and confidential info like cash balance., cost price of our products or supplier problems. 
>
> Keep the shop rules as you suggested before. I like the ladder and other our own rules. keep them I will also add that the boss can add any tools the agent needs to MCP server so that they can work on open tickets effectively. But such new tools should be added after the boss ask me for approval with the correct idea on why that tool is needed. Shop facts come from the MCP server over data/campus_customer_new.db. Never invent a secon shop tools layer that bypasses MCP.

**Follow-up prompt (mid-task):**
> Wire the agent so they append to output/audit_trail.json as they run. For each time the agent runs, record enough to audit later. Append the audit to the file and never wipe it.
> In. outptut/harness.md, list each agent and each mcp tool. The prompt asks to add new tools too. So maybe the tools that we initially had (i guess 9 tools) add the remaining 6 too into the harness.md and also assign these tools to the agents in their prompts. Along with this in the harness, add which table the tool uses. Add a short safetly section. I beleive we already have one but think more about it in terms ofare there any other things that we would want agent to know when agents touch real customers and real money. Also make sure their is a rule to limit token use. Because we have added new tools, updated mcp_server/Readme,md

**What happened:**
- Added an append-only audit trail (`backend/audit.py` → `output/audit_trail.json`, JSON Lines). It records run start and end, every agent run (who asked, question, typed output, tokens), every MCP tool call, delegations, refusals, board items and human approvals. It is never rewritten.
- Added 6 MCP tools to reach 9: `list_open_tickets`, `resolve_ticket`, `list_vendors`, `get_pricing`, `get_cash_balance`, `get_lease`. `make_payment` can also pay a restock purchase order (priced from `pricing`, refused while the vendor has an open invoice).
- Assigned the tools to agents in their prompts and in `team.py`. No agent gets `make_payment`; only a human approval calls it.
- Rewrote the harness tool section with all 9 tools (tables read and written, agent, tickets, why), plus Agent Team, Loop limits, Safety, Token budget and Audit trail sections.
- Added shop rules 19–24 ("real customers, real money") and rule 25 (token budget), backed by hard limits in code.
- Updated `mcp_server/README.md`.
- Tested the 9 tools on a throwaway database copy, and tested the team offline with a scripted model: delegation, guards and audit all worked, and the working database was unchanged.
- **Note on Accounting:** my prompt said Accounting should "add money into the account balance", but the assignment says cash only goes out, so Accounting only subtracts (and never inflates the balance).

---

## Problem 6: Desk Tickets Page (output/desk_tickets.html)

**Prompt:**
> Now onto problem 6.  I want you to build output/desk_tickets.html. This is a page where I can double click with one tab per ticket (101.102.103). Also add empty cash and reflection tabs for later problems. Leave them blank for now. In each of the ticket tab have 'expected' section and 'actual' section. In the expected section wrtite down waht we experct the team to do with that open ticket. leave the actaly section to be filled once the agents perform the task. In the expected section. 
> for ticket 1, the boss should call the accountant to make the payment first with a human approval. Then it should call the supplier to get the replrint order place and then call the cusomer service to draft a message on when their order will. be out. (klet me now know if i have gone wrong somewhere)
> For ticket 2: The boss calls the faciliteis department to prapre the payment for human approval
> For ticket 4: The boss first calls inventory to check if there is stock, then it makes sure that the facilities makes sure that the facilities preapre the payment for the unpaid invoice. Now that the payment has made, the bioss works with accounting to determine what should be the price after discount to ensure that the we are able to meet the order of the custeomr. 
>
> Do a fact cehck if this expected section is corect and make changes if need. The plan is to ensure that every specialist is not involved in the ticket.

**What the fact check changed:**
- **#101:** Accounting only *prepares* the payment; the human makes it by approving. Inventory needs to check the stock first. "Call the supplier to place the reprint" was dropped, because the rules ban contacting vendors and invoice 501 already *is* the rush reprint, so paying it unblocks shipping (arrival 2026-09-05).
- **#102:** Facilities finds and flags the rent but delegates to Accounting to prepare the payment.
- **#103:** It's #103, not "ticket 4". Accounting, not Facilities, handles invoice 501, which is already requested on #101, so it isn't paid twice. Nothing is paid until the human approves. A discount can't fund the restock, because no money comes in: after rent and 501 only $160 is left, which buys 7 hoodies, so the club gets 15 of 20 with any discount kept at or above the $31.43 cost floor.
- Each ticket tab shows which specialists work on it and which stay out (#101 and #103: no Facilities; #102: no Inventory or Customer Service).

---

## Problem 7: Backend Routes (FastAPI)

**Prompt:**
> Onto problem 7. I want to creat backend routes. In backend/main.py use fastapi and add routes that do the following. 
>
> 1. return three tickets and whether each is open or resolved
> 2. take a ticket id and run your agent team on that ticket
> 3. return recent agent event, what each agent said and which tool they used so the board cna refresh
> 4. approve a payment or purchse after a human click on it
> 5. return the current checking balance from cash_accounts
> 6. reset the db to the orgiginal value when you want to try a fresh run.

**Follow-up prompt (mid-task):**
> Record this in output/harness.md, list each route in one line

**Follow-up prompt (mid-task):**
> i hope you are recoding stuff in ai_prompts.md

**What happened:**
- Built `backend/main.py` with the 6 routes: tickets, run team on a ticket, events, approve payment, cash, reset. Added 2 extras the dashboard needs: `GET /api/board` and reject a payment.
- Added a 10th MCP tool, `list_tickets`, so the ticket list (including resolved tickets) still comes through MCP and not straight from the database.
- The board now persists between runs until a reset, so a run on one ticket sees the payments other tickets already requested.
- Tested every route in-process with a scripted model (no tokens spent):
  - an unknown ticket gives 404, and starting a second run while one is going gives 409;
  - the events show each agent, what it said and which tool it used;
  - a blank approver gives 422, approving gives paid with cash $3,400 → $2,560, and approving twice gives 409;
  - reset brings the cash back to $3,400 and the working database matches the original again.
- Also checked that the live uvicorn server answers. Listed each route in one line in `output/harness.md`.

**Prompt:**
> From the backend/ folder, start the server with uvicorn main:app --reload --port 8000

---

## Problem 8: React Dashboard (frontend/)

**Prompt:**
> Onto problem 8. Build a front end dashboard in frontend/ witih react, vite, typescript. . The dashboard should do the following
>
> 1. List all the three ticekts
> 2. Let the user pick  which ticket should be first attempted at solving
> 3. Show what each agent are saying and doing. Show in simple terms so that the user can understand
> 4. mark a ticket resolved when the run finsihes,
> 5. A short summary on what the agent did
> 6. Let human approve a pay or purchase when asked
> 7. Show the checking balance. It should drop adter an approved pay
> 8. Designt the dashboard with the same theme as campus customs webiste like last time. Make sure its user friendsly and looks complete and well structures

**What happened:**
- Built the dashboard in `frontend/` (React + Vite + TypeScript) with the Campus Customs theme from HW4. It has:
  - a ticket board with a Run button per ticket, so I choose the order;
  - a plain-English live feed of what each agent says and does, and which tool it used;
  - a ticket summary written by the Boss;
  - an approvals queue (Approve / Reject with my name);
  - a checking-balance card that drops after a payment;
  - the team roster and a reset button.
- **Backend additions:**
  - the Boss now writes a plain-English `summary` for each ticket;
  - events carry the tool's inputs and results, so the feed can describe them simply;
  - tickets are **marked resolved automatically** (through MCP `resolve_ticket`) once the run is done and every payment for that ticket is approved.
- **Testing:**
  - drove the real backend code with a scripted model on a demo port (no tokens) and took headless-Chrome screenshots;
  - fixed the feed scrolling the whole page, a duplicate "Refused:" in messages, and duplicated events caused by React's development mode;
  - the hoodie order approved first was refused (vendor blocked); rent and invoice 501 dropped cash to $160 and resolved #101 and #102;
  - reset the database afterwards, and kept the demo out of the real audit trail.

**Follow-up prompt:**
> In the same problem 8. Tell the front end to talk to your backend at http://localhost:8000. On the backend allow the vite page origin so that the browser can call those routes. Start the board with npm run dev. Write the output/design.md with how the dashboard is deisnged i.e how is the layout, how agennts read diffrently, how resolved tickets and cash flow show up

**What happened:**
- The frontend now calls the backend directly at `http://localhost:8000` (`frontend/src/api.ts`, `VITE_API_URL` to override), instead of going through the Vite proxy.
- The backend's CORS already allowed the Vite origin. I verified it: the browser's preflight for POST returns `access-control-allow-origin: http://localhost:5173`, and another website gets no permission.
- Restarted the dashboard with `npm run dev` (http://localhost:5173). The page loads live tickets and cash from port 8000.
- Wrote `output/design.md`: theme, layout (choose → watch → decide), how each agent reads differently (avatar, colour, motto, plain-English sentences, speech bubbles, indentation, tone colours), how resolved tickets show up (badges, green cards, automatic resolve through MCP, summary panel), and how cash flow shows up (balance card, waiting/left-after, "−$X paid just now" flash, approvals in ladder order, refusals). Screenshots are in `output/design_images/`.

---

## Problem 9: Test the Agents

**Prompt:**
> Onto problem 9. Before testing the agents, reset the working database. Tell the starting checking balance

**What happened:** Reset the working database through the backend's `POST /api/reset`. `campus_customs_new.db` is byte-identical to the original again, and the board is clean. Starting checking balance: **$3,400.00** (as of 2026-08-31). No payments, all 3 tickets open, invoice 501 open, rent due 2026-09-02. The reset was appended to `output/audit_trail.json`.

**Follow-up prompt (with a screenshot of the dashboard error):**
> there is an erro

**What was lacking:** The first real run on #101 stopped straight away. Portkey/Azure returned a 400 error: `gpt-6-luna` doesn't allow function tools with reasoning on the chat-completions endpoint, and suggested `/v1/responses`. The offline tests used a scripted model, so they never touched this real API and couldn't catch it.

**Fix:** Switched `backend/model_config.py` from `OpenAIChatModel` to `OpenAIResponsesModel` (still `gpt-6-luna` through Portkey, the only model). Set reasoning effort to `low` and raised the per-reply cap to 4,000 tokens, because reasoning tokens count towards it. Checked with two tiny real calls: a tool call, and a tool call with a typed answer. Both worked. The failed run changed nothing in the database. Updated the harness.

**Follow-up prompt (with a screenshot of the approvals panel):**
> it does not let me approve

**What was lacking:** The Approve button is locked until a name is typed in "Approving as", because the name is saved as `approved_by` on the payment. The only explanation was a hover tooltip, so it looked broken. Now, when a payment is waiting and the name is empty, the field is outlined in coral with the message "↑ Type your name first. It's recorded as the approver on every payment."

**Follow-up prompt (with a screenshot of ticket #103's feed ending in an error):**
> whats happening?

**What was lacking (found in `output/audit_trail.json`):**
1. **Token cap too low:** Customer Service's final answer hit the 4,000-token limit (reasoning tokens count towards it), and the error crashed the whole run. Raised the cap to 16,000. A teammate's failure now comes back as "couldn't finish" instead of stopping the run.
2. **Cash double-counted (my bug):** the board subtracted *approved* payments from a balance they had already left. After rent was paid ($3,400 → $1,000), Accounting still subtracted the $2,400 and thought there was no cash at all. Now only *pending* requests count as committed, and the prompt and board say so.
3. **Invoice vs vendor id:** Accounting called `check_vendor_can_ship(501)` with the invoice id. Accounting now has `list_vendors` (an existing tool, not a new one) and its prompt explains how to find an invoice through its vendor.
4. **Guessed SKU:** Inventory was asked without the ticket's details and guessed "CC-TEE-BULLDOG". The Boss now passes the ticket's own sku/size/qty/invoice_id/lease_id in every hand-off, and Inventory must never guess a SKU and must always report the full picture (stock, vendor, blocked or not, arrival).
5. **Customer Service too early:** the Boss delegated to all three teammates at once. Parallel tool calls are off now, and the Boss prompt says facts first, money second, Customer Service last.
- That's why #101 came out "blocked" with no payment request, and why #103's draft said there was no cash.
- Re-ran the offline route tests (they all pass) and restored the database to the state I had left it in.

**Prompt:**
> stop runing as i will complete this hw later

**What happened:** Stopped the backend (uvicorn on port 8000), the dashboard (Vite on port 5173) and any MCP server processes. Nothing was reset. The working database stays as it was, with rent paid and checking at $1,000.

**Prompt (returning to the homework):**
> which problem were we on?

**Prompt:**
> Okay fix those two problems , reset the database and give me the link to open the dashboard so that i can run the agents

**What happened:**
1. **Tickets closed too early:** a ticket now closes only when every payment **and** every customer draft for it is approved. The Boss's own `resolve_ticket` is refused while anything is still waiting. Added routes and dashboard buttons to approve or reject customer messages (they're still never sent). The Boss prompt now explains when to use `waiting_on_human`, `blocked` and `resolved`.
2. **Missed partial restock:** the Accounting prompt now says to prepare a purchase order for the largest quantity that fits (`floor(available ÷ unit_cost)`, e.g. $160 ÷ $22 = 7 hoodies for $154), after the blocking invoice. The Boss prompt says "partial beats nothing": offer what's on the shelf plus that restock, and be honest about the rest.
- Offline test (scripted model): the Boss's early close was refused; the ticket stayed open after the payment was approved and resolved only after the draft was approved; approving the draft twice was refused.
- Reset the database, started the backend and dashboard, and updated `output/harness.md` and `output/design.md`.

**Follow-up prompt:**
> why is the ticket not getting resolved?

**What happened:** #103 wasn't stuck. Its run was still going: the Boss hadn't made its decision yet, and a ticket can only close after that. I had approved the order and the message while the run was still in progress. The run was slow because Customer Service hit the 16,000-token limit (the model's reasoning ran on) after it had already saved its draft. The Boss carried on without it, decided at 23:45:53, and #103 was marked resolved one second later. All three tickets are now resolved; checking is $20.

**Follow-up prompt:**
> why was the 8 dollar debited?

**What happened:** The $8 was payment request #2 on ticket #101: a purchase order for 1 × CC-TEE-WHITE size S at its $8 unit cost, prepared by Accounting at 23:39:32 and approved on the dashboard at 23:40:13. The Boss had asked Accounting to check "purchase-order cost/ability to order the one needed tee". Nothing in the prompts says that invoice 501 ("Rush reprint CC-TEE-WHITE S", the ticket's own `invoice_id`) already *is* the order for that tee. So the team treated paying 501 as only unblocking the vendor, and ordered the tee again. This is a gap in my prompts: the database can't confirm what the reprint contains, but the ticket links to that invoice and the description names the same SKU and size, so a second order was most likely a duplicate. It also cost #103 a hoodie: $152 left instead of $160 → 6 hoodies instead of 7.

**Prompt:**
> Okay I think first the order matters. If i run the first ticket first then the agents should pay the bill and place the order for small tee as we domnt have the invenotry for it. This is because the supplier would not make more unless we pay them. Also we need to wait for 5 days after the bill is paied to give it to our customers. So mentionning that in our message is important. I dont know where the 8dollar debit went, so fix taht. I dont think that should have happended. Then when it comes to ticekt 2 then pay the rent with my approval and thats it. Then on the third ticket, because the shop only has 8 but cusomter needs 20. We are in short of 12. So we need to first place the order for remaining 12 (i dont know why we just ordered 6 in the previous attempt). But this can be ordered only if ticket 1 is resolved. So incase i start this tickdt first then ensure that ticket 1 is run and is resolved too. So you need to interact and test if there are dependancy with other tickets to solve a ticket or not as well. now i believe I cannot purchase all 12 since I might not have the money to give to the supplier. If that happens then the agents have to figure out a way to either ask the customer to purchase a partial order and then give purchase the other part later. But the boss and agent need to creative to figure out how the problem can be resolvd. CAn we make a partial order now and give the customer some discount on future order so that they approve the delay. Or is there some other way. Also if discount is given you need to take my approval

**What happened:**
- **The $8:** it was a purchase order for 1 × CC-TEE-WHITE S, paid to Bulldog Print Co and recorded in `payments`. It was a duplicate, because invoice 501 *is* the reprint of that tee. Now the prompts say paying the ticket's own invoice is the order, and the board **refuses** a purchase order for an item the ticket's invoice already covers.
- **#101 message:** Customer Service must say the item is ready "about N days after we release the restock" (5 days for Bulldog Print Co, on or about Sept 5), and never mention bills or payments. Customer Service now runs with reasoning effort `none`, which also fixed it running out of tokens.
- **#103 order of work:** the new Boss tool `solve_ticket_first` works a ticket this one depends on. Invoice 501 belongs to #101, so running #103 first solves #101 first.
  - The board files an invoice payment under the ticket that owns it.
  - It links a purchase order to the invoice payment that unblocks the vendor; the dashboard locks that Approve button until the invoice is approved.
  - It sets aside rent due within 30 days before any stock spending, even if #102 hasn't been run.
- **#103 12 hoodies:** Accounting tries all 12 first. If they don't fit, it orders the most that fit (7 for $154).
- **Creative fix:** the Boss's default is a goodwill discount (this order or the next) for waiting. Accounting's `prepare_discount_request` puts it on the board for **my approval** and refuses anything below the Cost Floor. The dashboard has Approve/Reject discount cards, and a ticket only resolves when its payments, discounts and messages are all approved.
- **Budgets:** limits are now per ticket (80 requests, 120 tool calls, 400k tokens), and a prerequisite ticket gets its own budget. The first real #103-first run ran out at 60 requests before the Boss could decide.
- **Testing:**
  - **Scripted (no tokens):** the dependency was detected; the duplicate tee was refused; 12 was refused and 7 accepted; a 60% discount was refused by the Cost Floor and 10% accepted; the purchase order couldn't be approved before 501; everything resolved after approval.
  - **Real `gpt-6-luna` run of #103 first (no approvals):** the Boss spotted the dependency and solved #101 first; no duplicate tee order; rent set aside; a purchase order for 7 linked to 501; finished with 15 + 29 requests.
  - **Customer Service check:** a quick real test confirmed the 5-day wording and the discount in the message.
- Updated `output/harness.md`, `output/design.md` and the **Expected** sections of `output/desk_tickets.html`. Reset the database for my run.

**Prompt:**
> Okay now tell me for each task, which agents were run, what did they delegate and which tools were used

**What happened:** Summarised my run (101 → 102 → 103) from `output/audit_trail.json`: which agents ran, who delegated to whom, which MCP tools each used, what was requested and approved, and tokens per ticket. Final cash was $6 ($3,400 − $840 − $2,400 − $154) and all three tickets resolved. Gaps found:
- #101 skipped Inventory, so there was no `check_stock`.
- Tauhid's message still mentions "approval" and doesn't say "about 5 days".
- #103 offered no goodwill discount, despite the new default.
- The team-only tools (`view_board`, `delegate`, etc.) show up in the trail only through their effects, not as tool calls.

**Prompt:**
> Okay fix it and reset the database. Also now open the output/desk_tickets.html. On the ticket tabl, firll the acutal section with what the agents run. Tell which agenets worke, what they delegater and which tools they used. on the cash tab of the same html, itemize the money. Which meanss that start with checking balance (after reset). Then for each ticket show how cash changed when tat ticket resolved and why and then show ending cheking balance. This must aand must match cash_accounts in teh wo4rknig database. Also save output/resolved_ticekts.josn for each ticket. there should be id, final status,. short outcome, what each agent contributed, and any human approvals. Similary output/resolved_bord.html. A page I double ckilck with a ss of the reach board for each resolved ticekt. Append the real runs to output/audit_trail.json. Finish harness.md so it covers tables, mcp tools, the five agents, api routes,the dashboard and safetly rules

**Follow-up prompt:**
> Okay maybe fix the error and then let me run the agents on the website and then you create the report?

**What happened:**
- Fixed the four gaps with checks in code, not just prompts:
  1. The Boss's decision on a customer order is sent back if Inventory never checked the stock.
  2. It's also sent back if the customer is left short with no goodwill discount and no "No goodwill discount because…".
  3. Customer drafts are refused if they mention approvals, invoices, payments, suppliers or cash, or if the item isn't on the shelf and the message doesn't say how many days.
  4. The team's own tools are now logged in the audit trail (`team_tool_call`).
- Tested with a scripted model: every check fired. Reset the database. The report (Actual sections, Cash tab, `resolved_tickets.json`, `resolved_board.html`, harness) will be made after I run the tickets on the website.

**Prompt:**
> i am done

**What happened:**
- **Captured the finished run:** board, events and tickets saved to `output/run_snapshot.json`, and a dashboard screenshot of each resolved ticket plus the whole board saved in `output/resolved_board_images/`.
- **Built `scripts/build_report.py`:** it creates every report from the real data (snapshot, audit trail, databases):
  - `desk_tickets.html` **Actual** cards: agents that worked, delegations step by step, tools per agent, approvals, automatic checks. Ticket headers now show ✓ resolved.
  - **Cash** tab: $3,400 → −$840 (#101 invoice 501) → −$2,400 (#102 rent) → −$154 (#103 restock) = **$6**, verified against `cash_accounts`.
  - `output/resolved_tickets.json` and `output/resolved_board.html`.
- **Real mistake found in the run:** the hoodie order used vendor id 2 (Elm City Gifts) while naming "Bulldog Print Co" as the payee, so Elm City Gifts was paid. The report flags it. The board now refuses a purchase order whose payee doesn't match its vendor id (and a rent payee that isn't the landlord), and the Accounting prompt says to use the vendor id Inventory reported.
- **My mistake:** a scripted test reset the working database after the run. I restored it exactly by replaying the run's recorded `make_payment` and `resolve_ticket` calls through MCP (payments, cash, invoices, lease and ticket notes all match the snapshot), and recorded a `db_restore` note in the audit trail.
- **Audit trail:** the real runs are already appended to `output/audit_trail.json`, including the new `team_tool_call` records.
- **Finished `output/harness.md`:** contents, tables, MCP tools, the five agents, the agent loop and limits, a full Safety section (all 28 shop rules plus the guards enforced in code), API routes, dashboard, audit trail, reports and the real run, and how to run it end to end.

---

## Problem 10: Reflection (desk_tickets.html → Reflection tab)

**Prompt:**
> now onto problem 10. open output/desk_tickets.html and i need to fill the reflection tab according to the questions in the ss
>
> 1. The performance of the agents were better with iteractions on each ticket. It makes a lot of errors like buysing a tshirt and debiting that money from the account even though the ticket did not ask for it. then the agent did not look through pther tickets while executing the task. then the agents sometime completely ignored delegating the task to a specified agent like inventory handler
> 2. The actual in my first iteration did not work well with the expected value. For some reason the agent debited an extra tee shirt from the account. But this was resolved in further iterations. 
> 3. It would not have needed to delegate the task, so an extra step for boss to think which tasks to delegate would not have happened. Agents talking to one another while multiple tasks are running is complicating the process, there are communication issues within agents. each agent might interpret what the other agent said in a different way. Some agents might just get ignored and that resulted in wrong results. These are the problems that will be caused which would have been reolved if only one agent were there
> 4. a) If the rent is due before I get the revenue from the custeomer and the order to the supplier has to be place, then this agent would not place that order until the money is set aside for the rent. b) It can decode the amoiunt of discount that needs to be given to the customer out of goodwill c) (write sometthin you think fits)
> 5. 1) It would not be able to recommend new items that the custeomr can purshcase incase the item the custoemr requested for is not there. I could use the inventory agent and look for similar products in the databse that are the similar cost and shocase that to the user 2) Campus customs team might face the difficulty on getting delayed order from the supplier, this agent cannot predict this or solve such logistic issues. I would use the accounting agent to determine if there are has been such delays in payement sna delivery in the past and accunt for that delay in my estimateion 3_) figure out something and fill this point
> 6. I need to write all these points in my own vibe, it should not be AI generic so refine it =, edit it if needed but make sure it seems likeits in my own vibe

**What happened:** Filled the **Reflection** tab in `output/desk_tickets.html`, keeping my own points and wording, cleaned up and in plain first person. Facts were checked against the real runs:
- Added the hoodie vendor mix-up to Q1 and Q2, and the token cost to Q3.
- Wrote 4c myself: "half an order beats saying no" (8 now + 7 later instead of refusing).
- Wrote 5.3 myself: the customer can't reply, so the club's choice never comes back into the system.
- Noted under 5.2 that the database only has payment dates, so delivery dates would have to be recorded.
- No screenshot came through with the prompt, so the question headings are taken from my five answers.

**Follow-up prompt (with a screenshot of the five reflection questions):**
> this was the ss

**What happened:** Rewrote the Reflection tab to match the five real questions, keeping my wording and voice.
- **Q1 and Q2** are now answered per ticket: #101 started bad and ended good; #102 matched every time; #103 had good decisions but paid the wrong supplier, so the system's arrival (Sept 3) differs from what the club was told (Sept 5).
- **Q3** is my single-agent answer.
- **Q4** turns my rent-first and goodwill-discount ideas into *new* problems the team could solve, plus a third: a Crest Mug order (0 in stock, Elm City Gifts, 3 days, $3.50 each), using the same tools.
- **Q5** covers alternative products, supplier delays and customer replies, each with the tools/tables (and agent) needed: `find_similar_products`, a deliveries table with `get_delivery_history`, and a customer replies table with `log_customer_reply` / `reopen_ticket`.

---

## Problem 11: Push to GitHub

**Prompt (with screenshots of the expected file layout and README requirements):**
> Okay onto problem 11. Push the code to my public github repo. Put the repo URL in output/github_url.txt. The structure of the project should be like the ss provided

**What happened:**
- Matched the required layout:
  - renamed `mcp_server/mcp_server.py` → `mcp_server/server.py`;
  - merged the two requirements files into a root `requirements.txt`;
  - made `.mcp.json` use paths relative to the project root, so it works on any machine (the backend resolves them);
  - changed `.gitignore` so **both databases are committed** and `.env` is not;
  - wrote the root `README.md`: clean copy of the database, start MCP server, start backend, start React board, reset before a full three-ticket run.
- Checked the backend and `.mcp.json` still start the server with all 10 tools.
- Scanned every staged file for the real Portkey key and other tokens: none found. `.env`, `.venv` and `node_modules` are excluded.
- Wrote `output/github_url.txt`, committed, and pushed to a new public repo, https://github.com/Rishabh200398/hw5.
