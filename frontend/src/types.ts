// Shapes returned by the FastAPI backend (backend/main.py).

export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Fact {
  claim: string
  source: string
}

export interface TicketDecision {
  ticket_id: number
  decision: string
  summary: string
  reasoning: string
  status: 'resolved' | 'waiting_on_human' | 'blocked'
  facts: Fact[]
}

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  notes: string | null
  status: 'open' | 'resolved'
  team_status: TicketDecision['status'] | null
  decision: TicketDecision | null
}

export interface TeamEvent {
  id: number
  run_id: string
  at: string
  ticket_id: number
  kind:
    | 'start' | 'delegate' | 'report' | 'tool_call' | 'payment_request' | 'draft' | 'tool_request'
    | 'decision' | 'refused' | 'error' | 'human_action' | 'resolved' | 'end' | 'discount_request' | 'dependency'
  agent: AgentName
  to: AgentName | null
  tool: string | null
  data: { args?: Record<string, unknown>; result?: unknown } | null
  text: string
  depth: number
}

export interface EventsResponse {
  running: boolean
  current_run: string | null
  last_event: number
  events: TeamEvent[]
}

export type ApprovalStatus = 'pending' | 'approved' | 'rejected'

export interface PaymentRequest {
  id: number
  ticket_id: number
  kind: 'invoice' | 'rent' | 'purchase_order'
  ref_id: number
  payee: string
  amount: number
  balance_before: number
  balance_after: number
  ladder_rank: number
  reason: string
  sku: string | null
  size: string | null
  qty: number | null
  depends_on: number[]
  status: ApprovalStatus
  approved_by: string | null
  result: Record<string, unknown> | null
}

export interface DiscountRequest {
  id: number
  ticket_id: number
  customer: string
  kind: 'this_order' | 'future_order'
  sku: string
  qty: number
  list_price: number
  unit_cost: number
  discount_pct: number
  discounted_price: number
  margin_pct: number
  floor_price: number
  reason: string
  status: ApprovalStatus
  approved_by: string | null
}

export interface CustomerDraft {
  id: number
  ticket_id: number
  to: string
  subject: string
  body: string
  facts_used: Fact[]
  status: ApprovalStatus
  approved_by: string | null
}

export interface ToolRequest {
  id: number
  ticket_id: number
  tool_name: string
  what_it_does: string
  unlocks: string
  status: ApprovalStatus
}

export interface Board {
  board_id: string
  running: boolean
  payment_requests: PaymentRequest[]
  discount_requests: DiscountRequest[]
  cash_committed_to_pending: number
  drafts: CustomerDraft[]
  tool_requests: ToolRequest[]
  decisions: Record<string, TicketDecision>
  model_requests: number
}

export interface Cash {
  name: string
  balance: number
  date: string
}
