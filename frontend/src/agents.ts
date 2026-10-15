import type { AgentName } from './types'

export interface AgentProfile {
  name: string
  role: string
  motto: string
  icon: string
  color: string
}

// Matches the prompts in backend/prompts/*.md
export const AGENTS: Record<AgentName, AgentProfile> = {
  boss: {
    name: 'Boss', role: 'The Dispatcher', icon: '🐶', color: '#00366b',
    motto: 'Every ticket gets an owner, a decision and a reason.',
  },
  inventory: {
    name: 'Inventory', role: 'The Stockroom Detective', icon: '📦', color: '#2f7d4f',
    motto: "If it's not on the shelf, I find out when it will be.",
  },
  accounting: {
    name: 'Accounting', role: 'The Penny Guardian', icon: '💰', color: '#b26a00',
    motto: "Cash only flows one way here: out. Spend it like it's the last.",
  },
  facilities: {
    name: 'Facilities', role: 'The Landlord Whisperer', icon: '🏢', color: '#6b4fa3',
    motto: 'Keep the lights on and the doors open.',
  },
  customer_service: {
    name: 'Customer Service', role: 'The Bulldog Voice', icon: '💬', color: '#f04f36',
    motto: 'Honest dates, warm words, no surprises.',
  },
}

export const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: n % 1 ? 2 : 0 })

export const LADDER: Record<number, string> = {
  1: 'Rent',
  2: 'Overdue bill blocking an order',
  3: 'New stock for an order',
  4: 'Discount / nice-to-have',
}
