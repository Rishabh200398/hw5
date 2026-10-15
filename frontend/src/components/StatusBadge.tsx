import type { Ticket } from '../types'

export type TicketState = 'open' | 'working' | 'waiting' | 'blocked' | 'resolved'

export function ticketState(t: Ticket, workingOn: number | null): TicketState {
  if (t.status === 'resolved') return 'resolved'
  if (workingOn === t.id) return 'working'
  if (t.team_status === 'waiting_on_human') return 'waiting'
  if (t.team_status === 'blocked') return 'blocked'
  return 'open'
}

const LABEL: Record<TicketState, string> = {
  open: 'Open',
  working: 'Team working…',
  waiting: 'Needs your approval',
  blocked: 'Blocked',
  resolved: 'Resolved',
}

export default function StatusBadge({ state }: { state: TicketState }) {
  return <span className={`badge badge-${state}`}>{state === 'resolved' ? '✓ ' : ''}{LABEL[state]}</span>
}
