import { useEffect, useRef, useState } from 'react'
import AppNav from '../components/AppNav'
import { Button, Badge } from '../ds'

interface LogData {
  lines: string[]
  total: number
}

function logLevel(line: string): 'error' | 'warn' | 'info' | 'dim' {
  const l = line.toLowerCase()
  if (l.includes('error') || l.includes('exception') || l.includes('traceback') || l.includes('critical')) return 'error'
  if (l.includes('warning') || l.includes('warn')) return 'warn'
  if (l.includes('info') || l.includes('started') || l.includes('ready')) return 'info'
  return 'dim'
}

function lineColor(level: string) {
  if (level === 'error') return 'var(--tawn-crit)'
  if (level === 'warn') return 'var(--tawn-warn)'
  if (level === 'info') return 'var(--tawn-good)'
  return 'var(--tawn-text-2)'
}

export function LogsPanel() {
  const [data, setData] = useState<LogData | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [n, setN] = useState(200)
  const bottomRef = useRef<HTMLDivElement>(null)

  function load() {
    fetch(`/api/logs?n=${n}`)
      .then((r) => r.json())
      .then((d: LogData) => setData(d))
      .catch(() => {})
  }

  useEffect(() => { load() }, [n])

  useEffect(() => {
    if (!autoRefresh) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [autoRefresh, n])

  useEffect(() => {
    if (data && autoRefresh) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [data])

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
        <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>
          ~/.tawn/web.log{data ? ` · ${data.total} total lines` : ''}
        </p>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            value={n}
            onChange={(e) => setN(Number(e.target.value))}
            style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', padding: '5px 8px', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', background: 'var(--tawn-surface)', color: 'var(--tawn-text)', cursor: 'pointer' }}
          >
            <option value={50}>last 50</option>
            <option value={200}>last 200</option>
            <option value={500}>last 500</option>
            <option value={99999}>all</option>
          </select>
          <Button size="sm" variant="secondary" onClick={load}>refresh</Button>
          <span
            onClick={() => setAutoRefresh((v) => !v)}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, fontFamily: 'var(--tawn-font-mono)', padding: '5px 10px', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', cursor: 'pointer', background: autoRefresh ? 'var(--tawn-lapis-soft)' : 'transparent', color: autoRefresh ? 'var(--tawn-lapis)' : 'var(--tawn-text-2)' }}
          >
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: autoRefresh ? 'var(--tawn-good)' : 'var(--tawn-line-strong)', animation: autoRefresh ? 'tawn-pulse 1.2s ease-in-out infinite' : 'none' }} />
            live
          </span>
        </div>
      </div>

      {!data ? (
        <div style={{ fontSize: 13, color: 'var(--tawn-text-2)', padding: '20px 0' }}>loading…</div>
      ) : data.lines.length === 0 ? (
        <div style={{ background: 'var(--tawn-raised)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', padding: '28px 20px', textAlign: 'center' }}>
          <div style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginBottom: 6 }}>no logs yet</div>
          <div style={{ fontSize: 12, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>start tawn web to populate this log</div>
        </div>
      ) : (
        <div style={{ background: 'var(--tawn-raised)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', overflow: 'hidden' }}>
          <div style={{ overflowY: 'auto', maxHeight: '60vh', padding: '12px 16px' }}>
            {data.lines.map((line, i) => (
              <div key={i} style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', lineHeight: 1.7, color: lineColor(logLevel(line)), whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {line}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
          <div style={{ borderTop: '1px solid var(--tawn-line)', padding: '7px 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Badge tone="neutral">{data.lines.length} lines shown</Badge>
            {autoRefresh && <Badge status="good">live · 3s</Badge>}
          </div>
        </div>
      )}
    </div>
  )
}

export default function Logs() {
  return (
    <div style={{ background: 'var(--tawn-bg)', minHeight: '100vh' }}>
      <AppNav />
      <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px 64px' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>logs</h1>
        <LogsPanel />
      </div>
    </div>
  )
}
