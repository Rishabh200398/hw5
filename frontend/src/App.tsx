import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE, ApiError, api } from './api'
import Approvals from './components/Approvals'
import ActivityFeed from './components/ActivityFeed'
import BulldogAvatar from './components/BulldogAvatar'
import CashCard from './components/CashCard'
import TeamRoster from './components/TeamRoster'
import TicketBoard from './components/TicketBoard'
import TicketSummary from './components/TicketSummary'
import type { AgentName, Board, Cash, TeamEvent, Ticket } from './types'

const POLL_RUNNING_MS = 1500
const POLL_IDLE_MS = 5000

function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as { request?: { result?: { error?: string } } } | string
    if (typeof d === 'object' && d?.request?.result?.error) return d.request.result.error
    return typeof d === 'string' ? d : e.message
  }
  return `Could not reach the backend at ${API_BASE}. Is it running?`
}

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [board, setBoard] = useState<Board | null>(null)
  const [cash, setCash] = useState<Cash | null>(null)
  const [events, setEvents] = useState<TeamEvent[]>([])
  const [running, setRunning] = useState(false)
  const [selected, setSelected] = useState<number | null>(() => Number(new URLSearchParams(location.search).get('ticket')) || null)
  const [filterFeed, setFilterFeed] = useState(true)
  const [approver, setApprover] = useState(() => localStorage.getItem('approver') ?? '')
  const [toast, setToast] = useState<{ text: string; kind: 'ok' | 'err' } | null>(null)
  const lastId = useRef(0)
  const wasRunning = useRef(false)

  const notify = (text: string, kind: 'ok' | 'err' = 'ok') => {
    setToast({ text, kind })
    setTimeout(() => setToast(null), 5000)
  }

  const refresh = useCallback(async () => {
    try {
      const [t, b, c] = await Promise.all([api.tickets(), api.board(), api.cash()])
      setTickets(t)
      setBoard(b)
      setCash(c)
    } catch (e) {
      notify(errorText(e), 'err')
    }
  }, [])

  // Poll for new agent events; refresh tickets, board and cash whenever something changes.
  useEffect(() => {
    let stop = false
    let timer: ReturnType<typeof setTimeout>
    const tick = async () => {
      try {
        const r = await api.events(lastId.current)
        if (stop) return  // this poller was cleaned up while the request was in flight
        if (r.last_event < lastId.current) {  // the board was reset
          lastId.current = 0
          setEvents([])
        }
        if (r.events.length) {
          lastId.current = r.events[r.events.length - 1].id
          setEvents((prev) => {
            const seen = new Set(prev.map((e) => e.id))
            return [...prev, ...r.events.filter((e) => !seen.has(e.id))]
          })
        }
        setRunning(r.running)
        const changed = r.events.some((e) => ['payment_request', 'discount_request', 'draft', 'decision', 'resolved', 'end', 'human_action'].includes(e.kind))
        if (changed || (wasRunning.current && !r.running)) await refresh()
        wasRunning.current = r.running
      } catch {
        /* backend not up yet; keep trying */
      }
      if (!stop) timer = setTimeout(tick, wasRunning.current ? POLL_RUNNING_MS : POLL_IDLE_MS)
    }
    refresh()
    tick()
    return () => {
      stop = true
      clearTimeout(timer)
    }
  }, [refresh])

  useEffect(() => localStorage.setItem('approver', approver), [approver])

  const run = async (id: number) => {
    setSelected(id)
    setFilterFeed(true)
    try {
      await api.run(id)
      setRunning(true)
      wasRunning.current = true
      notify(`The team picked up ticket #${id}.`)
    } catch (e) {
      notify(errorText(e), 'err')
    }
  }

  const approve = async (id: number) => {
    try {
      const r = await api.approve(id, approver.trim())
      notify(`Paid ${r.request.payee}. The checking balance has been updated.`)
    } catch (e) {
      notify(`Payment refused: ${errorText(e).replace(/^Refused: /, '')}`, 'err')
    }
    await refresh()
  }

  const reject = async (id: number) => {
    try {
      await api.reject(id, approver.trim())
      notify('Payment rejected. Nothing was paid.')
    } catch (e) {
      notify(errorText(e), 'err')
    }
    await refresh()
  }

  const approveDiscount = async (id: number) => {
    try {
      await api.approveDiscount(id, approver.trim())
      notify('Discount approved. No money moved; it sets the price offered to the customer.')
    } catch (e) {
      notify(errorText(e), 'err')
    }
    await refresh()
  }

  const rejectDiscount = async (id: number) => {
    try {
      await api.rejectDiscount(id, approver.trim())
      notify('Discount rejected. The ticket stays open so the team can rethink the offer.')
    } catch (e) {
      notify(errorText(e), 'err')
    }
    await refresh()
  }

  const approveDraft = async (id: number) => {
    try {
      await api.approveDraft(id, approver.trim())
      notify('Message approved. It stays on the board and is never sent automatically.')
    } catch (e) {
      notify(errorText(e), 'err')
    }
    await refresh()
  }

  const rejectDraft = async (id: number) => {
    try {
      await api.rejectDraft(id, approver.trim())
      notify('Message rejected. The ticket stays open so the team can try again.')
    } catch (e) {
      notify(errorText(e), 'err')
    }
    await refresh()
  }

  const reset = async () => {
    if (!confirm('Reset the shop database to its original values and clear the board? (The audit trail is kept.)')) return
    try {
      await api.reset()
      lastId.current = 0
      setEvents([])
      setSelected(null)
      notify('Fresh start: the database is back to its original values.')
    } catch (e) {
      notify(errorText(e), 'err')
    }
    await refresh()
  }

  const workingOn = running ? [...events].reverse().find((e) => e.kind === 'start')?.ticket_id ?? null : null
  const runOrder = Array.from(new Set(events.filter((e) => e.kind === 'start').map((e) => e.ticket_id)))
  const lastAgent: AgentName | null = running && events.length ? events[events.length - 1].agent : null
  const pendingCount = (board?.payment_requests.filter((p) => p.status === 'pending').length ?? 0)
    + (board?.drafts.filter((d) => d.status === 'pending').length ?? 0)
    + (board?.discount_requests.filter((d) => d.status === 'pending').length ?? 0)
  const openCount = tickets.filter((t) => t.status === 'open').length

  return (
    <div className="app">
      <header className="site-header">
        <div className="announcement">Operations Desk · Every payment needs a human signature · Drafts are never sent automatically</div>
        <nav className="navbar">
          <div className="brand">
            <span className="brand-mark">CC</span>
            <span className="brand-text">Campus Customs<small>Operations Desk</small></span>
          </div>
          <div className="nav-right">
            <span className={`run-dot ${running ? 'on' : ''}`}>{running ? 'Team working' : 'Team idle'}</span>
            {pendingCount > 0 && <span className="nav-pill">{pendingCount} to approve</span>}
            <button className="btn btn-outline btn-small" onClick={reset} disabled={running}>↺ Reset database</button>
          </div>
        </nav>
      </header>

      <section className="hero">
        <div className="hero-inner">
          <BulldogAvatar size={64} />
          <div>
            <p className="eyebrow">Campus Customs Multi-Agent Operations</p>
            <h1>{openCount === 0 && tickets.length ? 'All tickets resolved. Nice work!' : `${openCount} ticket${openCount === 1 ? '' : 's'} on the board`}</h1>
            <ol className="steps">
              <li><b>1</b> Pick a ticket</li>
              <li><b>2</b> Watch the team work it</li>
              <li><b>3</b> Approve or reject payments</li>
            </ol>
          </div>
        </div>
      </section>

      <main className="layout">
        <div className="col col-left">
          <TicketBoard
            tickets={tickets}
            selected={selected}
            workingOn={workingOn}
            running={running}
            runOrder={runOrder}
            onSelect={(id) => { setSelected(id); setFilterFeed(true) }}
            onRun={run}
          />
        </div>

        <div className="col col-center">
          <TicketSummary
            ticket={tickets.find((t) => t.id === selected)}
            events={events}
            payments={board?.payment_requests ?? []}
            drafts={board?.drafts ?? []}
            workingOn={workingOn}
          />
          <ActivityFeed
            events={events}
            running={running}
            ticketFilter={filterFeed ? selected : null}
            onClearFilter={() => setFilterFeed(false)}
          />
        </div>

        <div className="col col-right">
          <CashCard cash={cash} pending={board?.cash_committed_to_pending ?? 0} />
          <Approvals
            requests={board?.payment_requests ?? []}
            discounts={board?.discount_requests ?? []}
            drafts={board?.drafts ?? []}
            approver={approver}
            onApproverChange={setApprover}
            onApprove={approve}
            onReject={reject}
            onApproveDiscount={approveDiscount}
            onRejectDiscount={rejectDiscount}
            onApproveDraft={approveDraft}
            onRejectDraft={rejectDraft}
          />
          <TeamRoster active={lastAgent} />
        </div>
      </main>

      <footer className="footer">
        Campus Customs · Chapel Street, New Haven · Agents run on gpt-6-luna via Portkey · Shop facts come only from the campus-customs MCP server
      </footer>

      {toast && <div className={`toast toast-${toast.kind}`} role="status">{toast.text}</div>}
    </div>
  )
}
