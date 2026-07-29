import { useEffect, useState } from 'react'
import { listHistory, getHistorySession, SessionMeta, HistoryEntry } from '../lib/api'
import { useErrors } from '../components/Errors'

export default function History() {
  const { report } = useErrors()
  const reportError = (e: unknown) => report(e instanceof Error ? e.message : String(e))
  const [sessions, setSessions] = useState<SessionMeta[]>([])
  const [active, setActive] = useState<string | null>(null)
  const [entries, setEntries] = useState<HistoryEntry[]>([])

  useEffect(() => {
    listHistory().then(setSessions).catch(reportError)
  }, [])

  function openSession(id: string) {
    setActive(id)
    getHistorySession(id).then(setEntries).catch(() => setEntries([]))
  }

  return (
    <main style={{ maxWidth: 900, margin: '40px auto', padding: '0 20px' }}>
      <h1 style={{ fontFamily: 'var(--tawn-font-display)', fontSize: 28, marginBottom: 8 }}>
        chat history
      </h1>
      <p style={{ color: 'var(--tawn-text-2)', fontSize: 13, marginBottom: 28 }}>
        private, stored only at <code>~/.tawn/history/</code> (chmod 700). never synced anywhere.
      </p>

      <div style={{ display: 'flex', gap: 24 }}>
        {/* session list */}
        <div style={{ width: 260, flexShrink: 0 }}>
          {sessions.length === 0 ? (
            <p style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>no sessions yet — start chatting</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {sessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => openSession(s.id)}
                  style={{
                    textAlign: 'left',
                    background: active === s.id ? 'var(--tawn-surface)' : 'transparent',
                    border: '1px solid ' + (active === s.id ? 'var(--tawn-lapis)' : 'var(--tawn-line)'),
                    borderRadius: 6,
                    padding: '10px 12px',
                    cursor: 'pointer',
                    color: 'var(--tawn-text)',
                  }}
                >
                  <div style={{ fontSize: 12, color: 'var(--tawn-text-2)' }}>
                    {s.started.replace('T', ' ').slice(0, 16)}
                  </div>
                  <div style={{ fontSize: 13, marginTop: 2 }}>
                    {s.turns} turn{s.turns !== 1 ? 's' : ''}
                    {s.model ? <span style={{ color: 'var(--tawn-text-2)' }}> · {s.model}</span> : null}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* session detail */}
        <div style={{ flex: 1 }}>
          {active && entries.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {entries.filter((e) => e.role !== 'system').map((e, i) => (
                <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ fontSize: 11, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                    {e.role} · {e.ts.replace('T', ' ').slice(0, 19)}
                  </div>
                  <div
                    style={{
                      background: e.role === 'user' ? 'transparent' : 'var(--tawn-surface)',
                      border: '1px solid var(--tawn-line)',
                      borderRadius: 8,
                      padding: '12px 16px',
                      fontSize: 14,
                      lineHeight: 1.6,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {e.content}
                  </div>
                  {e.tokens_out > 0 && (
                    <div style={{ fontSize: 11, color: 'var(--tawn-text-2)' }}>
                      {e.tokens_in}→{e.tokens_out} tok
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : active ? (
            <p style={{ fontSize: 14, color: 'var(--tawn-text-2)' }}>loading…</p>
          ) : (
            <p style={{ fontSize: 14, color: 'var(--tawn-text-2)' }}>select a session to view</p>
          )}
        </div>
      </div>
    </main>
  )
}
