import { AGENTS } from '../agents'
import type { AgentName } from '../types'
import BulldogAvatar from './BulldogAvatar'

export default function AgentAvatar({ agent, size = 34, active = false }: { agent: AgentName; size?: number; active?: boolean }) {
  const a = AGENTS[agent]
  return (
    <span
      className={`agent-avatar ${active ? 'active' : ''}`}
      style={{ width: size, height: size, borderColor: a.color, background: `${a.color}14` }}
      title={`${a.name}: ${a.role}`}
    >
      {agent === 'boss' ? <BulldogAvatar size={size - 6} /> : <span style={{ fontSize: size * 0.5 }}>{a.icon}</span>}
    </span>
  )
}
