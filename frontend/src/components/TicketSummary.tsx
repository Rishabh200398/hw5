import { useState } from 'react'
import { AGENTS, money } from '../agents'
import type { AgentName, CustomerDraft, PaymentRequest, TeamEvent, Ticket } from '../types'
import AgentAvatar from './AgentAvatar'
import StatusBadge, { ticketState } from './StatusBadge'

interface Props {
  ticket: Ticket | undefined
  events: TeamEvent[]
  payments: PaymentRequest[]
  drafts: CustomerDraft[]
  workingOn: number | null
}

export default function TicketSummary({ ticket, events, payments, drafts, workingOn }: Props) {
  const [showWhy, setShowWhy] = useState(false)
  if (!ticket) {
    return (
      <section className="panel summary-panel">
        <h2>Ticket summary</h2>
        <p className="muted">Select a ticket on the left to see what the team did with it.</p>
      </section>
    )
  }
  const mine = events.filter((e) => e.ticket_id === ticket.id)
  const agents = Array.from(new Set(mine.flatMap((e) => [e.agent, e.to]).filter(Boolean))) as AgentName[]
  const checks = mine.filter((e) => e.kind === 'tool_call').length
  const handoffs = mine.filter((e) => e.kind === 'delegate').length
  const stops = mine.filter((e) => e.kind === 'refused').length
  const pays = payments.filter((p) => p.ticket_id === ticket.id)
  const myDrafts = drafts.filter((d) => d.ticket_id === ticket.id)
  const d = ticket.decision
  const state = ticketState(ticket, workingOn)

  return (
    <section className={`panel summary-panel state-${state}`}>
      <div className="panel-head">
        <h2>#{ticket.id} · {ticket.subject}</h2>
        <StatusBadge state={state} />
      </div>

      {!d && state !== 'working' && <p className="muted">The team hasn't worked this ticket yet.</p>}
      {!d && state === 'working' && <p className="muted">The team is on it. The summary appears when the run finishes.</p>}

      {d && (
        <>
          <p className="summary-text">{d.summary}</p>
          <div className="decision">
            <span className="decision-label">Boss's decision</span>
            <p>{d.decision}</p>
            <button className="text-link" onClick={() => setShowWhy(!showWhy)}>
              {showWhy ? 'Hide reasoning ▲' : 'Why? Show the reasoning ▼'}
            </button>
            {showWhy && (
              <div className="why">
                <p>{d.reasoning}</p>
                {d.facts.length > 0 && (
                  <ul className="facts">
                    {d.facts.map((f, i) => <li key={i}>{f.claim} <span className="muted">· {f.source}</span></li>)}
                  </ul>
                )}
              </div>
            )}
          </div>
        </>
      )}

      {mine.length > 0 && (
        <div className="stats">
          <div className="who-worked">
            {agents.map((a) => <AgentAvatar key={a} agent={a} size={28} />)}
            <span className="muted small">{agents.map((a) => AGENTS[a].name).join(', ')}</span>
          </div>
          <div className="stat-row">
            <span><b>{handoffs}</b> hand-offs</span>
            <span><b>{checks}</b> database checks</span>
            <span><b>{pays.length}</b> payment request{pays.length === 1 ? '' : 's'}</span>
            <span><b>{myDrafts.length}</b> draft{myDrafts.length === 1 ? '' : 's'}</span>
            {stops > 0 && <span className="warn"><b>{stops}</b> safety stop{stops === 1 ? '' : 's'}</span>}
          </div>
          {pays.length > 0 && (
            <ul className="mini-pays">
              {pays.map((p) => (
                <li key={p.id}>
                  {p.payee} · {money(p.amount)} · <span className={`pill pill-${p.status}`}>{p.status === 'pending' ? 'waiting for you' : p.status}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {myDrafts.map((dr) => (
        <details key={dr.id} className="draft">
          <summary>✉️ Draft to <b>{dr.to}</b>: {dr.subject} <span className={`pill pill-${dr.status}`}>{dr.status === 'pending' ? 'waiting for you' : dr.status}</span> <span className="muted small">(never sent automatically)</span></summary>
          <pre>{dr.body}</pre>
        </details>
      ))}
    </section>
  )
}
