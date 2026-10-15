import { useEffect, useRef, useState } from 'react'
import { money } from '../agents'
import type { Cash } from '../types'

export default function CashCard({ cash, pending }: { cash: Cash | null; pending: number }) {
  const prev = useRef<number | null>(null)
  const [drop, setDrop] = useState<number | null>(null)

  useEffect(() => {
    if (!cash) return
    if (prev.current !== null && cash.balance < prev.current) {
      setDrop(prev.current - cash.balance)
      const t = setTimeout(() => setDrop(null), 4000)
      prev.current = cash.balance
      return () => clearTimeout(t)
    }
    prev.current = cash.balance
  }, [cash])

  const after = cash ? cash.balance - pending : 0
  return (
    <section className={`panel cash-card ${drop ? 'dropped' : ''}`}>
      <span className="eyebrow-dark">Checking balance</span>
      <div className="balance">{cash ? money(cash.balance) : '…'}</div>
      {drop && <div className="drop">−{money(drop)} paid just now</div>}
      <dl className="cash-lines">
        <div><dt>Waiting for your approval</dt><dd>{money(pending)}</dd></div>
        <div className={after < 0 ? 'neg' : ''}><dt>Left if you approve all</dt><dd>{money(after)}</dd></div>
      </dl>
      <p className="muted small">Read live from <code>cash_accounts</code>{cash ? ` · as of ${cash.date}` : ''}. Cash only goes out; it can never go below $0.</p>
    </section>
  )
}
