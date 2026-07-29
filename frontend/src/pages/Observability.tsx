import { useEffect, useMemo, useState } from 'react'
import { Card, Input, Button, Badge } from '../ds'
import { useErrors } from '../components/Errors'
import {
  getEvents, getVerify, getSpend, getSpendStatus, postReconcile,
  getObserverSessions, postObserverReview,
  type AuditEvent, type ChainStatus, type SpendSummary, type SpendStatus,
  type ObserverSession,
} from '../lib/api'

function Stat({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: 'warn' | 'crit' }) {
  const colour = tone === 'crit' ? 'var(--tawn-crit)' : tone === 'warn' ? 'var(--tawn-warn)' : 'var(--tawn-text)'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 10.5, fontFamily: 'var(--tawn-font-mono)', letterSpacing: '0.09em', textTransform: 'uppercase', color: 'var(--tawn-text-3)' }}>
        {label}
      </span>
      <span style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.15, fontVariantNumeric: 'tabular-nums', color: colour }}>
        {value}
      </span>
      {note && <span style={{ fontSize: 12, color: 'var(--tawn-text-2)' }}>{note}</span>}
    </div>
  )
}

function GroupTable({ title, rows, keyName }: { title: string; rows: SpendSummary['by_operation']; keyName: 'operation' | 'provider' | 'caller' }) {
  if (rows.length === 0) return null
  return (
    <div>
      <div style={{ fontSize: 10.5, fontFamily: 'var(--tawn-font-mono)', letterSpacing: '0.09em', textTransform: 'uppercase', color: 'var(--tawn-text-3)', marginBottom: 8 }}>
        {title}
      </div>
      {rows.slice(0, 6).map((r) => (
        <div key={String(r[keyName])} style={{ display: 'flex', gap: 10, alignItems: 'baseline', padding: '5px 0', borderBottom: '1px solid var(--tawn-line)', fontSize: 12.5 }}>
          <span style={{ color: 'var(--tawn-text)' }}>{String(r[keyName]) || 'unknown'}</span>
          <span style={{ marginLeft: 'auto', fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-2)', fontVariantNumeric: 'tabular-nums' }}>
            {r.calls}
          </span>
          <span style={{ fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', fontVariantNumeric: 'tabular-nums', minWidth: 74, textAlign: 'right' }}>
            ${r.cost_usd.toFixed(4)}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function Observability() {
  const { report } = useErrors()
  const reportError = (e: unknown) => report(e instanceof Error ? e.message : String(e))
  const [spend, setSpend] = useState<SpendSummary | null>(null)
  const [status, setStatus] = useState<SpendStatus | null>(null)
  const [chain, setChain] = useState<ChainStatus | null>(null)
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [total, setTotal] = useState(0)
  const [actor, setActor] = useState('')
  const [opFilter, setOpFilter] = useState('')
  const [busy, setBusy] = useState(false)
  const [sessions, setSessions] = useState<ObserverSession[]>([])
  const [reviewing, setReviewing] = useState(false)

  function loadAll() {
    getSpend().then(setSpend).catch(reportError)
    getSpendStatus().then(setStatus).catch(reportError)
    getVerify().then(setChain).catch(reportError)
    getObserverSessions().then((p) => setSessions(p.sessions)).catch(reportError)
  }

  useEffect(loadAll, [])

  useEffect(() => {
    getEvents({ actor: actor || undefined, op: opFilter || undefined, limit: 60 })
      .then((p) => { setEvents(p.entries); setTotal(p.total) })
      .catch(reportError)
  }, [actor, opFilter])

  async function reconcile() {
    setBusy(true)
    try {
      await postReconcile()
      loadAll()
    } finally {
      setBusy(false)
    }
  }

  async function review() {
    setReviewing(true)
    try {
      await postObserverReview()
      loadAll()
    } finally {
      setReviewing(false)
    }
  }

  // A cost total that omits calls it could not price would understate spend,
  // so it is rendered as incomplete rather than as a bare figure.
  const costLabel = useMemo(() => {
    if (!spend) return '—'
    return `$${spend.total_cost_usd.toFixed(4)}`
  }, [spend])

  const stale = (status?.pending_bytes ?? 0) > 0

  return (
    <>
      <div style={{ maxWidth: 940, margin: '0 auto', padding: '32px 24px 64px' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>activity</h1>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginBottom: 20 }}>
          what your twin has been doing, and what it cost.
        </p>

        <Card style={{ marginBottom: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 18 }}>
            <Stat label="model calls" value={spend ? String(spend.total_calls) : '—'} />
            <Stat
              label="spend"
              value={costLabel}
              note={spend && spend.unpriced_calls > 0 ? `+ ${spend.unpriced_calls} unpriced` : undefined}
              tone={spend && spend.unpriced_calls > 0 ? 'warn' : undefined}
            />
            <Stat label="tokens in" value={spend ? spend.total_tokens_in.toLocaleString() : '—'} />
            <Stat
              label="audit chain"
              value={chain ? (chain.intact ? 'intact' : 'BROKEN') : '—'}
              note={chain ? (chain.intact ? `${chain.entries} entries` : `breaks at #${chain.first_break_index}`) : undefined}
              tone={chain && !chain.intact ? 'crit' : undefined}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--tawn-line)', flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11.5, fontFamily: 'var(--tawn-font-mono)', color: stale ? 'var(--tawn-warn)' : 'var(--tawn-text-3)' }}>
              {status?.last_reconciled
                ? `last reconciled ${new Date(status.last_reconciled).toLocaleString()}`
                : 'never reconciled'}
              {stale ? ` · ${status?.pending_bytes} bytes pending` : ''}
            </span>
            <Button variant="secondary" size="sm" onClick={reconcile} disabled={busy} style={{ marginLeft: 'auto' }}>
              {busy ? 'reconciling…' : 'reconcile now'}
            </Button>
          </div>
        </Card>

        {spend && spend.total_calls > 0 && (
          <Card style={{ marginBottom: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 22 }}>
              <GroupTable title="by operation" rows={spend.by_operation} keyName="operation" />
              <GroupTable title="by provider" rows={spend.by_provider} keyName="provider" />
              <GroupTable title="by caller" rows={spend.by_caller} keyName="caller" />
            </div>
          </Card>
        )}

        {sessions.length > 0 && (
          <Card style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 10.5, fontFamily: 'var(--tawn-font-mono)', letterSpacing: '0.09em', textTransform: 'uppercase', color: 'var(--tawn-text-3)' }}>
                work sessions
              </span>
              <Button variant="secondary" size="sm" onClick={review} disabled={reviewing} style={{ marginLeft: 'auto' }}>
                {reviewing ? 'writing…' : 'review now'}
              </Button>
            </div>
            {sessions.map((s) => (
              <div key={s.id} style={{ display: 'flex', gap: 10, alignItems: 'baseline', padding: '7px 0', borderBottom: '1px solid var(--tawn-line)', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 12.5, fontWeight: 600, fontFamily: 'var(--tawn-font-mono)' }}>{s.project}</span>
                <span style={{ fontSize: 12, color: 'var(--tawn-text-2)', flex: 1, minWidth: 140 }}>
                  {s.attribution}
                </span>
                <span style={{ fontSize: 11.5, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', fontVariantNumeric: 'tabular-nums' }}>
                  {s.event_count} files · +{s.lines_added} −{s.lines_removed}
                </span>
                {s.ended_at === null && <Badge status="info">open</Badge>}
                {s.note_state === 'pending_note' && <Badge status="warn">note pending</Badge>}
                <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', whiteSpace: 'nowrap' }}>
                  {s.started_at ? new Date(s.started_at).toLocaleString() : ''}
                </span>
              </div>
            ))}
          </Card>
        )}

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
          <Input placeholder="filter by operation…" value={opFilter} onChange={(e) => setOpFilter(e.target.value)} style={{ maxWidth: 220 }} />
          <select
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', padding: '5px 8px', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', background: 'var(--tawn-raised)', color: 'var(--tawn-text)' }}
          >
            <option value="">all actors</option>
            {['cli', 'web', 'chat', 'mcp', 'system'].map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)' }}>
            {total} event{total === 1 ? '' : 's'}
          </span>
        </div>

        <Card padded={false}>
          <div style={{ padding: '0 20px' }}>
            {events.length > 0 ? events.map((e, i) => (
              <div key={`${e.chain}-${i}`} style={{ display: 'flex', gap: 10, alignItems: 'baseline', padding: '9px 0', borderBottom: '1px solid var(--tawn-line)', flexWrap: 'wrap' }}>
                {!e.ok && <Badge status="warn">failed</Badge>}
                <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--tawn-text)', fontFamily: 'var(--tawn-font-mono)' }}>{e.op}</span>
                <span style={{ fontSize: 12, color: 'var(--tawn-text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, minWidth: 100 }}>
                  {e.target}
                </span>
                {e.actor && (
                  <span style={{ fontSize: 10.5, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', border: '1px solid var(--tawn-line)', borderRadius: 999, padding: '1px 7px' }}>
                    {e.actor}
                  </span>
                )}
                <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', whiteSpace: 'nowrap' }}>
                  {new Date(e.ts).toLocaleString()}
                </span>
              </div>
            )) : (
              <div style={{ padding: '24px 0', fontSize: 13, color: 'var(--tawn-text-2)', textAlign: 'center' }}>
                no events recorded yet.
              </div>
            )}
            <div style={{ height: 4 }} />
          </div>
        </Card>
      </div>
    </>
  )
}
