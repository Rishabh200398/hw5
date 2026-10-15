import { useState } from 'react'
import { LADDER, money } from '../agents'
import type { CustomerDraft, DiscountRequest, PaymentRequest } from '../types'

interface Props {
  requests: PaymentRequest[]
  discounts: DiscountRequest[]
  drafts: CustomerDraft[]
  approver: string
  onApproverChange: (name: string) => void
  onApprove: (id: number) => Promise<void>
  onReject: (id: number) => Promise<void>
  onApproveDiscount: (id: number) => Promise<void>
  onRejectDiscount: (id: number) => Promise<void>
  onApproveDraft: (id: number) => Promise<void>
  onRejectDraft: (id: number) => Promise<void>
}

const KIND: Record<PaymentRequest['kind'], string> = {
  invoice: 'Pay invoice',
  rent: 'Pay rent',
  purchase_order: 'Restock order',
}

export default function Approvals({ requests, discounts, drafts, approver, onApproverChange, onApprove, onReject, onApproveDiscount, onRejectDiscount, onApproveDraft, onRejectDraft }: Props) {
  const [busy, setBusy] = useState<number | null>(null)
  const pending = requests.filter((r) => r.status === 'pending').sort((a, b) => a.ladder_rank - b.ladder_rank)
  const done = requests.filter((r) => r.status !== 'pending')
  const pendingDrafts = drafts.filter((d) => d.status === 'pending')
  const doneDrafts = drafts.filter((d) => d.status !== 'pending')
  const pendingDiscounts = discounts.filter((d) => d.status === 'pending')
  const doneDiscounts = discounts.filter((d) => d.status !== 'pending')
  const waiting = pending.length + pendingDrafts.length + pendingDiscounts.length
  const blockers = (r: PaymentRequest) => requests.filter((p) => r.depends_on.includes(p.id) && p.status !== 'approved')
  const act = async (id: number, fn: (id: number) => Promise<void>) => {
    setBusy(id)
    try { await fn(id) } finally { setBusy(null) }
  }

  return (
    <section className="panel approvals">
      <div className="panel-head">
        <h2>Your approvals</h2>
        {waiting > 0 && <span className="count">{waiting}</span>}
      </div>
      <p className="hint">No money moves and no message is final until you click <b>Approve</b>. Payments are listed in Priority Ladder order. A ticket closes once everything for it is approved.</p>

      <label className={`approver ${waiting > 0 && !approver.trim() ? 'needs-name' : ''}`}>
        Approving as
        <input value={approver} onChange={(e) => onApproverChange(e.target.value)} placeholder="Type your name to approve" />
        {waiting > 0 && !approver.trim() && (
          <span className="name-hint">↑ Type your name first. It's recorded as the approver on every payment.</span>
        )}
      </label>

      {waiting === 0 && <p className="muted empty-small">Nothing waiting for you right now.</p>}

      {pending.map((r) => (
        <article key={r.id} className="pay-card">
          <div className="pay-top">
            <span className="pay-kind">{KIND[r.kind]}</span>
            <span className="pay-amount">{money(r.amount)}</span>
          </div>
          <p className="pay-to">to <b>{r.payee}</b> · ticket #{r.ticket_id}</p>
          {r.kind === 'purchase_order' && <p className="small">{r.qty} × {r.sku} size {r.size}</p>}
          <p className="small">{r.reason}</p>
          <p className="ladder">Rung {r.ladder_rank}: {LADDER[r.ladder_rank]}</p>
          {typeof r.result?.error === 'string' && <p className="pay-error">Last try was refused: {r.result.error.replace(/^Refused: /, '')}</p>}
          {blockers(r).length > 0 && (
            <p className="pay-wait">⏳ Approve first: {blockers(r).map((b) => `${KIND[b.kind]} ${money(b.amount)} to ${b.payee}`).join(', ')}. The vendor can't ship this until then.</p>
          )}
          <div className="pay-actions">
            <button
              className="btn btn-accent btn-small"
              disabled={!approver.trim() || busy !== null || blockers(r).length > 0}
              title={!approver.trim() ? 'Type your name first' : blockers(r).length ? 'Approve the payment it depends on first' : ''}
              onClick={() => act(r.id, onApprove)}
            >
              {busy === r.id ? 'Paying…' : `Approve ${money(r.amount)}`}
            </button>
            <button className="btn btn-ghost btn-small" disabled={!approver.trim() || busy !== null} onClick={() => act(r.id, onReject)}>
              Reject
            </button>
          </div>
        </article>
      ))}

      {pendingDiscounts.map((d) => (
        <article key={d.id} className="pay-card discount-card">
          <div className="pay-top">
            <span className="pay-kind">🏷️ Discount {d.kind === 'this_order' ? 'on this order' : 'on their next order'}</span>
            <span className="pay-amount">{d.discount_pct}% off</span>
          </div>
          <p className="pay-to">for <b>{d.customer}</b> · ticket #{d.ticket_id}</p>
          <p className="small">{d.qty} × {d.sku}: {money(d.list_price)} → <b>{money(d.discounted_price)}</b> each · margin {d.margin_pct}% (floor {money(d.floor_price)})</p>
          <p className="small">{d.reason}</p>
          <p className="small muted">No money moves. This only sets the price offered to the customer.</p>
          <div className="pay-actions">
            <button className="btn btn-primary btn-small" disabled={!approver.trim() || busy !== null}
              title={approver.trim() ? '' : 'Type your name first'} onClick={() => act(d.id, onApproveDiscount)}>
              {busy === d.id ? 'Saving…' : 'Approve discount'}
            </button>
            <button className="btn btn-ghost btn-small" disabled={!approver.trim() || busy !== null} onClick={() => act(d.id, onRejectDiscount)}>
              Reject
            </button>
          </div>
        </article>
      ))}

      {pendingDrafts.map((d) => (
        <article key={d.id} className="pay-card draft-card">
          <div className="pay-top">
            <span className="pay-kind">✉️ Customer message</span>
            <span className="muted small">ticket #{d.ticket_id}</span>
          </div>
          <p className="pay-to">to <b>{d.to}</b> · {d.subject}</p>
          <pre className="draft-body">{d.body}</pre>
          <p className="small muted">Approving marks it ready. It is never sent automatically.</p>
          <div className="pay-actions">
            <button className="btn btn-primary btn-small" disabled={!approver.trim() || busy !== null}
              title={approver.trim() ? '' : 'Type your name first'} onClick={() => act(d.id, onApproveDraft)}>
              {busy === d.id ? 'Saving…' : 'Approve message'}
            </button>
            <button className="btn btn-ghost btn-small" disabled={!approver.trim() || busy !== null} onClick={() => act(d.id, onRejectDraft)}>
              Reject
            </button>
          </div>
        </article>
      ))}

      {(done.length > 0 || doneDrafts.length > 0 || doneDiscounts.length > 0) && (
        <>
          <h3 className="sub-head">History</h3>
          <ul className="history">
            {done.map((r) => (
              <li key={r.id}>
                <span className={`pill pill-${r.status}`}>{r.status}</span> {KIND[r.kind]} {money(r.amount)} · {r.payee}
                {r.approved_by && <span className="muted"> · by {r.approved_by}</span>}
              </li>
            ))}
            {doneDiscounts.map((d) => (
              <li key={d.id}>
                <span className={`pill pill-${d.status}`}>{d.status}</span> {d.discount_pct}% off for {d.customer}
                {d.approved_by && <span className="muted"> · by {d.approved_by}</span>}
              </li>
            ))}
            {doneDrafts.map((d) => (
              <li key={d.id}>
                <span className={`pill pill-${d.status}`}>{d.status}</span> Message to {d.to}
                {d.approved_by && <span className="muted"> · by {d.approved_by}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
