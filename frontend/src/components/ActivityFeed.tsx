import { useEffect, useRef } from 'react'
import { AGENTS } from '../agents'
import { narrate } from '../narrate'
import type { TeamEvent } from '../types'
import AgentAvatar from './AgentAvatar'

interface Props {
  events: TeamEvent[]
  running: boolean
  ticketFilter: number | null
  onClearFilter: () => void
}

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export default function ActivityFeed({ events, running, ticketFilter, onClearFilter }: Props) {
  const shown = events.filter(
    (e) => ticketFilter === null || e.ticket_id === ticketFilter || (e.ticket_id === 0 && e.kind !== 'start'),
  )
  // Keep the newest step in view by scrolling the feed itself, never the whole page.
  const feed = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = feed.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [shown.length])

  return (
    <section className="panel feed-panel">
      <div className="panel-head">
        <h2>Live from the back office</h2>
        {ticketFilter !== null ? (
          <button className="chip-btn" onClick={onClearFilter}>Showing #{ticketFilter} · show all ✕</button>
        ) : (
          <span className="muted small">All tickets</span>
        )}
      </div>

      <div className="feed" ref={feed}>
        {shown.length === 0 && (
          <div className="empty">
            <p><b>Nothing yet.</b></p>
            <p className="muted">Pick a ticket and press <i>Run the team</i>. You'll see each agent's steps here, in plain English.</p>
          </div>
        )}
        {shown.map((e) => {
          const line = narrate(e)
          const a = AGENTS[e.agent]
          return (
            <div key={e.id} className={`feed-item tone-${line.tone}`} style={{ marginLeft: Math.min(e.depth, 3) * 18 }}>
              <AgentAvatar agent={e.agent} size={32} />
              <div className="feed-body">
                <div className="feed-meta">
                  <b style={{ color: a.color }}>{e.kind === 'human_action' ? 'You' : a.name}</b>
                  <span className="muted">· #{e.ticket_id || 'board'} · {time(e.at)}</span>
                  {e.tool && <code className="tool-tag">{e.tool}</code>}
                </div>
                <p>{line.text}</p>
                {line.quote && <blockquote>{line.quote}</blockquote>}
              </div>
            </div>
          )
        })}
        {running && (
          <div className="working">
            <span className="dots"><i /><i /><i /></span> The team is working. New steps appear here as they happen.
          </div>
        )}
      </div>
    </section>
  )
}
