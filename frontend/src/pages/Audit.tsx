import { useEffect, useState } from 'react'
import AppNav from '../components/AppNav'
import { Button, Badge } from '../ds'
import { getAudit, verifyAudit, type AuditPage } from '../lib/api'

const PAGE = 50

export function AuditPanel() {
  const [data, setData] = useState<AuditPage>({ total: 0, entries: [] })
  const [offset, setOffset] = useState(0)
  const [intact, setIntact] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)
  const [verifying, setVerifying] = useState(false)

  function load(off: number) {
    setLoading(true)
    getAudit(PAGE, off)
      .then((d) => { setData(d); setOffset(off) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(0) }, [])

  async function verify() {
    setVerifying(true)
    try {
      const r = await verifyAudit()
      setIntact(r.intact)
    } catch {
      setIntact(false)
    } finally {
      setVerifying(false)
    }
  }

  const start = offset + 1
  const end = Math.min(offset + PAGE, data.total)

  return (
    <div>
      {/* toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        <span style={{ fontSize: 12, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)', marginRight: 4 }}>
          {data.total} entries
        </span>
        <Button size="sm" variant="secondary" onClick={verify} disabled={verifying}>
          {verifying ? 'verifying…' : 'verify chain'}
        </Button>
        <Button size="sm" variant="secondary" onClick={() => { const a = document.createElement('a'); a.href='/api/audit/export?format=json'; a.download='tawn-audit.json'; a.click() }}>
          export JSON
        </Button>
        <Button size="sm" variant="secondary" onClick={() => { const a = document.createElement('a'); a.href='/api/audit/export?format=csv'; a.download='tawn-audit.csv'; a.click() }}>
          export CSV
        </Button>
        {intact !== null && (
          <Badge status={intact ? 'good' : 'crit'}>
            {intact ? 'chain intact' : 'chain broken — possible tampering'}
          </Badge>
        )}
      </div>

      {/* table */}
      {loading ? (
        <div style={{ fontSize: 13, color: 'var(--tawn-text-2)', padding: '20px 0' }}>loading…</div>
      ) : data.entries.length === 0 ? (
        <div style={{ background: 'var(--tawn-raised)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', padding: '28px 20px', textAlign: 'center' }}>
          <div style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>no audit entries yet</div>
          <div style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginTop: 4, fontFamily: 'var(--tawn-font-mono)' }}>entries appear when tawn records FS access, grant changes, or model calls</div>
        </div>
      ) : (
        <div style={{ border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: 'var(--tawn-surface)', borderBottom: '1px solid var(--tawn-line)' }}>
                  {['time', 'op', 'target', 'ok', 'chain'].map((h) => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--tawn-text-2)', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.entries.map((e, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--tawn-line)', background: i % 2 === 0 ? 'transparent' : 'var(--tawn-raised)' }}>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', whiteSpace: 'nowrap' }}>
                      {e.ts.replace('T', ' ').slice(0, 19)}
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-lapis)', whiteSpace: 'nowrap' }}>
                      {e.op}
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--tawn-font-mono)', fontSize: 11, color: 'var(--tawn-text-2)', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={e.target}>
                      {e.target}
                    </td>
                    <td style={{ padding: '8px 12px' }}>
                      <Badge status={e.ok ? 'good' : 'crit'}>{e.ok ? 'ok' : 'fail'}</Badge>
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--tawn-font-mono)', fontSize: 11, color: 'var(--tawn-text-3)', whiteSpace: 'nowrap' }}>
                      {e.chain.slice(0, 10)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* pagination */}
          {data.total > PAGE && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderTop: '1px solid var(--tawn-line)', background: 'var(--tawn-surface)' }}>
              <Button size="sm" variant="secondary" onClick={() => load(Math.max(0, offset - PAGE))} disabled={offset === 0}>← prev</Button>
              <span style={{ fontSize: 12, color: 'var(--tawn-text-2)', fontFamily: 'var(--tawn-font-mono)' }}>
                {start}–{end} of {data.total}
              </span>
              <Button size="sm" variant="secondary" onClick={() => load(offset + PAGE)} disabled={offset + PAGE >= data.total}>next →</Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function Audit() {
  return (
    <div style={{ background: 'var(--tawn-bg)', minHeight: '100vh' }}>
      <AppNav />
      <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px 64px' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>audit log</h1>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginBottom: 20 }}>
          append-only, chain-verified. every filesystem access, grant change, and model call recorded.
        </p>
        <AuditPanel />
      </div>
    </div>
  )
}
