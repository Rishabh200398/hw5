import { AGENTS } from '../agents'
import type { AgentName } from '../types'
import AgentAvatar from './AgentAvatar'

export default function TeamRoster({ active }: { active: AgentName | null }) {
  return (
    <section className="panel roster">
      <h2>Meet the team</h2>
      <ul>
        {(Object.keys(AGENTS) as AgentName[]).map((k) => (
          <li key={k} className={active === k ? 'active' : ''}>
            <AgentAvatar agent={k} size={36} active={active === k} />
            <div>
              <b>{AGENTS[k].name}</b> <span className="muted small">{AGENTS[k].role}</span>
              <p className="motto">“{AGENTS[k].motto}”</p>
            </div>
            {active === k && <span className="live">working</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}
