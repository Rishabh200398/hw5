// Thin client for the backend routes. The browser calls the FastAPI backend directly;
// the backend's CORS settings allow this page's origin (http://localhost:5173).
import type { Board, Cash, EventsResponse, PaymentRequest, Ticket } from './types'

export const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `Request failed (${status})`)
    this.status = status
    this.detail = detail
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? body)
  return body as T
}

export const api = {
  tickets: () => call<Ticket[]>('/tickets'),
  run: (ticketId: number) => call<{ run_id: string }>(`/tickets/${ticketId}/run`, { method: 'POST' }),
  events: (after: number) => call<EventsResponse>(`/events?after=${after}`),
  board: () => call<Board>('/board'),
  cash: () => call<Cash>('/cash'),
  approve: (id: number, approvedBy: string) =>
    call<{ paid: boolean; request: PaymentRequest }>(`/payments/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy }),
    }),
  reject: (id: number, by: string) =>
    call<{ rejected: boolean }>(`/payments/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: by }),
    }),
  approveDiscount: (id: number, approvedBy: string) =>
    call<{ approved: boolean }>(`/discounts/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy }),
    }),
  rejectDiscount: (id: number, by: string) =>
    call<{ rejected: boolean }>(`/discounts/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: by }),
    }),
  approveDraft: (id: number, approvedBy: string) =>
    call<{ approved: boolean }>(`/drafts/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy }),
    }),
  rejectDraft: (id: number, by: string) =>
    call<{ rejected: boolean }>(`/drafts/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: by }),
    }),
  reset: () => call<{ cash: Cash }>('/reset', { method: 'POST' }),
}
