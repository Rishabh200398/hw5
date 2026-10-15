// Turns raw agent events into short, plain-English sentences for the activity feed.
import { AGENTS, money } from './agents'
import type { TeamEvent } from './types'

type R = Record<string, any>

export interface Line {
  text: string
  quote?: string // something the agent "said", shown as a speech bubble
  tone: 'info' | 'talk' | 'money' | 'stop' | 'done' | 'human'
}

const who = (a: string | null | undefined) => (a ? AGENTS[a as keyof typeof AGENTS]?.name ?? a : '')

function toolLine(e: TeamEvent): Line {
  const args = (e.data?.args ?? {}) as R
  const raw = e.data?.result as R | R[] | undefined
  const r = (Array.isArray(raw) ? { list: raw } : raw ?? {}) as R
  const me = who(e.agent)
  if (r.error) return { text: `${me} tried “${e.tool}”, but it was refused: ${String(r.error).replace(/^Refused: /, '')}`, tone: 'stop' }
  switch (e.tool) {
    case 'list_open_tickets':
      return { text: `${me} read the ticket board: ${r.list?.length ?? 0} open ticket(s).`, tone: 'info' }
    case 'check_stock':
      return {
        text: r.in_stock
          ? `${me} checked the shelf: ${r.name} size ${r.size} has ${r.qty} on hand, enough for ${r.qty_needed}.`
          : `${me} checked the shelf: ${r.name} size ${r.size} has ${r.qty === 0 ? 'none' : `only ${r.qty}`} on hand. Short by ${r.shortfall}.`,
        tone: 'info',
      }
    case 'list_vendors':
      return { text: `${me} looked up the suppliers: ${(r.list ?? []).map((v: R) => `${v.name} (${v.specialty}, ${v.lead_days} day${v.lead_days === 1 ? '' : 's'})`).join(', ')}.`, tone: 'info' }
    case 'check_vendor_can_ship': {
      if (r.can_ship) return { text: `${me} checked ${r.name}: they can ship. Delivery on or about ${r.arrival_if_ordered_today}.`, tone: 'info' }
      const inv = (r.blocked_by_open_invoices ?? [])[0] ?? {}
      return {
        text: `${me} checked ${r.name}: they won't ship until we pay invoice #${inv.id} (${money(inv.amount ?? 0)}, ${inv.days_overdue} days overdue). Once paid, delivery is on or about ${r.arrival_if_ordered_today}.`,
        tone: 'stop',
      }
    }
    case 'get_cash_balance':
      return { text: `${me} checked the bank: ${money(r.balance)} in checking.`, tone: 'money' }
    case 'get_pricing':
      return { text: `${me} looked up the price of ${r.sku}: costs us ${money(r.unit_cost)}, sells for ${money(r.list_price)}. Lowest price we allow: ${money(r.cost_floor_price)}.`, tone: 'money' }
    case 'get_lease':
      return { text: `${me} checked the lease: ${money(r.monthly_rent)} rent to ${r.landlord}, due ${r.next_due} (${r.days_until_due} days away).`, tone: 'money' }
    case 'view_board':
      return { text: `${me} checked what's already waiting for your approval.`, tone: 'info' }
    case 'resolve_ticket':
      return { text: `${me} closed ticket #${args.ticket_id} and wrote down why.`, tone: 'done' }
    default:
      return { text: `${me} used the “${e.tool}” tool.`, tone: 'info' }
  }
}

export function narrate(e: TeamEvent): Line {
  const me = who(e.agent)
  switch (e.kind) {
    case 'start': return { text: `${e.text}.`, tone: 'info' }
    case 'tool_call': return toolLine(e)
    case 'delegate': return { text: `${me} asked ${who(e.to)} for help:`, quote: e.text, tone: 'talk' }
    case 'report': return { text: `${me} reported back to ${who(e.to)}:`, quote: e.text, tone: 'talk' }
    case 'payment_request': return { text: `${me} prepared a payment and is waiting for your approval: ${e.text.replace(/^#\d+ /, '').replace(/ - waiting for human approval$/, '')}.`, tone: 'money' }
    case 'draft': return { text: `${me} wrote a ${e.text.replace(/^draft #\d+ /, 'draft ')}. It waits for your approval and is never sent automatically.`, tone: 'talk' }
    case 'discount_request': return { text: `${me} proposed a discount and is waiting for your approval: ${e.text.replace(/^#\d+ /, '').replace(/ - waiting for human approval$/, '')}.`, tone: 'money' }
    case 'dependency': return { text: e.text.startsWith('Back on') ? `${me}: ${e.text}` : `${me} spotted a dependency: ${e.text}`, tone: 'talk' }
    case 'tool_request': return { text: `${me} asked you to add a new tool: ${e.text.replace(/^requested MCP tool /, '')}`, tone: 'human' }
    case 'refused': return { text: `A safety rule stopped ${me}: ${e.text.replace(/^.*?: /, '')}`, tone: 'stop' }
    case 'decision': return { text: `${me} made the call:`, quote: e.text.replace(/^\[[a-z_]+\] /, ''), tone: 'done' }
    case 'human_action': return { text: e.text, tone: 'human' }
    case 'resolved': return { text: e.text, tone: 'done' }
    case 'error': return { text: `Something went wrong: ${e.text}`, tone: 'stop' }
    case 'end': return { text: e.text.includes('completed') ? 'The team finished this run.' : `The run stopped early (${e.text.replace('run finished: ', '')}).`, tone: e.text.includes('completed') ? 'done' : 'stop' }
  }
}
