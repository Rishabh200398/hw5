import type { Ticket } from '../types'
import StatusBadge, { ticketState } from './StatusBadge'

const TYPE_LABEL: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Discount request',
}

function whatItNeeds(t: Ticket): string {
  if (t.type === 'rent_notice') return `Rent on lease #${t.lease_id}`
  const item = `${t.qty} × ${t.sku} · size ${t.size}`
  return t.invoice_id ? `${item} · linked to invoice #${t.invoice_id}` : item
}

interface Props {
  tickets: Ticket[]
  selected: number | null
  workingOn: number | null
  running: boolean
  runOrder: number[]
  onSelect: (id: number) => void
  onRun: (id: number) => void
}

export default function TicketBoard({ tickets, selected, workingOn, running, runOrder, onSelect, onRun }: Props) {
  const resolved = tickets.filter((t) => t.status === 'resolved').length
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Ticket board</h2>
        <span className="muted small">{resolved} of {tickets.length} resolved</span>
      </div>
      <p className="hint">
        <b>You choose the order.</b> Pick a ticket and press <i>Run the team</i>. Tip: the shop's Priority Ladder pays
        rent first, then overdue bills that block an order, then new stock.
      </p>

      <ul className="ticket-list">
        {tickets.map((t) => {
          const state = ticketState(t, workingOn)
          const order = runOrder.indexOf(t.id)
          return (
            <li
              key={t.id}
              className={`ticket-card state-${state} ${selected === t.id ? 'selected' : ''}`}
              onClick={() => onSelect(t.id)}
            >
              <div className="ticket-top">
                <span className="ticket-id">#{t.id}</span>
                <StatusBadge state={state} />
              </div>
              <h3>{t.subject}</h3>
              <p className="ticket-meta">
                <span className="tag">{TYPE_LABEL[t.type] ?? t.type}</span> from <b>{t.requester}</b>
              </p>
              <p className="ticket-needs">{whatItNeeds(t)}</p>
              {t.notes && <p className="ticket-note">“{t.notes.split('\n')[0]}”</p>}
              <div className="ticket-actions">
                {order >= 0 && <span className="run-order">Attempted {ordinal(order + 1)}</span>}
                {t.status !== 'resolved' && (
                  <button
                    className="btn btn-primary btn-small"
                    disabled={running}
                    onClick={(e) => {
                      e.stopPropagation()
                      onRun(t.id)
                    }}
                    title={running ? 'Wait for the current run to finish' : `Run the agent team on #${t.id}`}
                  >
                    {workingOn === t.id ? 'Running…' : order >= 0 ? 'Run again' : '▶ Run the team'}
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      {tickets.length === 0 && <p className="muted">Loading tickets… (is the backend running at http://localhost:8000?)</p>}
      <p className="muted small">Ticket details are read live from the shop database through MCP.</p>
    </section>
  )
}

function ordinal(n: number) {
  return n === 1 ? '1st' : n === 2 ? '2nd' : n === 3 ? '3rd' : `${n}th`
}
