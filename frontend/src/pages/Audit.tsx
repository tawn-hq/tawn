import { useEffect, useState } from 'react'
import { getAudit, verifyAudit, AuditPage } from '../lib/api'

const PAGE = 50

export default function Audit() {
  const [data, setData] = useState<AuditPage>({ total: 0, entries: [] })
  const [offset, setOffset] = useState(0)
  const [intact, setIntact] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)

  function load(off: number) {
    setLoading(true)
    getAudit(PAGE, off)
      .then((d) => { setData(d); setOffset(off) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(0) }, [])

  function verify() {
    verifyAudit().then((r) => setIntact(r.intact)).catch(() => setIntact(false))
  }

  function exportFile(fmt: 'json' | 'csv') {
    window.open(`/api/audit/export?format=${fmt}`, '_blank')
  }

  return (
    <main style={{ maxWidth: 900, margin: '40px auto', padding: '0 20px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginBottom: 8 }}>
        <h1 style={{ fontFamily: 'var(--tawn-font-display)', fontSize: 28, margin: 0 }}>
          audit log
        </h1>
        <span style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>
          {data.total} entries
        </span>
      </div>

      <p style={{ color: 'var(--tawn-text-2)', fontSize: 13, marginBottom: 20 }}>
        append-only, chain-verified. every filesystem access, grant change, and model call recorded.
      </p>

      <div style={{ display: 'flex', gap: 10, marginBottom: 24, flexWrap: 'wrap' }}>
        <button onClick={verify} style={btnStyle}>verify chain</button>
        <button onClick={() => exportFile('json')} style={btnStyle}>export JSON</button>
        <button onClick={() => exportFile('csv')} style={btnStyle}>export CSV</button>
        {intact !== null && (
          <span style={{ fontSize: 13, color: intact ? '#4c4' : '#e55', alignSelf: 'center' }}>
            {intact ? '✓ chain intact' : '✗ chain broken — possible tampering'}
          </span>
        )}
      </div>

      {loading ? (
        <p style={{ color: 'var(--tawn-text-2)', fontSize: 14 }}>loading…</p>
      ) : data.entries.length === 0 ? (
        <p style={{ color: 'var(--tawn-text-2)', fontSize: 14 }}>no audit entries yet</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--tawn-line)', color: 'var(--tawn-text-2)', textAlign: 'left' }}>
              {['time', 'op', 'target', 'ok', 'chain'].map((h) => (
                <th key={h} style={{ padding: '6px 10px', fontWeight: 500, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.entries.map((e, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--tawn-line)' }}>
                <td style={cellStyle}>{e.ts.replace('T', ' ').slice(0, 19)}</td>
                <td style={{ ...cellStyle, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-lapis)' }}>{e.op}</td>
                <td style={{ ...cellStyle, fontFamily: 'var(--tawn-font-mono)', fontSize: 11, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.target}</td>
                <td style={{ ...cellStyle, color: e.ok ? '#4c4' : '#e55' }}>{e.ok ? '✓' : '✗'}</td>
                <td style={{ ...cellStyle, fontFamily: 'var(--tawn-font-mono)', fontSize: 11, color: 'var(--tawn-text-2)' }}>{e.chain.slice(0, 8)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {data.total > PAGE && (
        <div style={{ display: 'flex', gap: 10, marginTop: 16, justifyContent: 'center' }}>
          <button onClick={() => load(Math.max(0, offset - PAGE))} disabled={offset === 0} style={btnStyle}>← prev</button>
          <span style={{ fontSize: 13, color: 'var(--tawn-text-2)', alignSelf: 'center' }}>
            {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
          </span>
          <button onClick={() => load(offset + PAGE)} disabled={offset + PAGE >= data.total} style={btnStyle}>next →</button>
        </div>
      )}
    </main>
  )
}

const btnStyle: React.CSSProperties = {
  background: 'var(--tawn-surface)',
  border: '1px solid var(--tawn-line)',
  borderRadius: 6,
  padding: '7px 14px',
  fontSize: 13,
  color: 'var(--tawn-text)',
  cursor: 'pointer',
}

const cellStyle: React.CSSProperties = {
  padding: '8px 10px',
  verticalAlign: 'top',
}
