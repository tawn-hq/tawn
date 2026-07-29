import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { StatCard, Card, Badge, Table, Button } from '../ds'
import { useErrors } from '../components/Errors'
import { getStatus, getDomains, getAudit, getChunkStats, getNotes, type DomainRow, type AuditEntry, type PersonalNote } from '../lib/api'

function useIsMobile() {
  const [m, setM] = useState(() => typeof window !== 'undefined' && window.innerWidth < 640)
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 639px)')
    const h = (e: MediaQueryListEvent) => setM(e.matches)
    mq.addEventListener('change', h)
    return () => mq.removeEventListener('change', h)
  }, [])
  return m
}

const KNOWN_DOMAINS = ['work', 'wealth', 'research', 'academic', 'hobby'] as const
type KnownDomain = typeof KNOWN_DOMAINS[number]

function DomainTile({ domain, onClick, delay }: { domain: DomainRow; onClick: () => void; delay: number }) {
  const [hover, setHover] = useState(false)
  const [visible, setVisible] = useState(false)
  const key = KNOWN_DOMAINS.includes(domain.name as KnownDomain) ? domain.name as KnownDomain : undefined

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay)
    return () => clearTimeout(t)
  }, [delay])

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        border: `1px solid ${hover ? 'var(--tawn-lapis)' : 'var(--tawn-line)'}`,
        borderRadius: 'var(--tawn-radius)',
        background: 'var(--tawn-surface)',
        padding: '16px 20px',
        cursor: 'pointer',
        minHeight: 90,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        gap: 12,
        transition: 'border-color 0.2s, transform 0.2s, opacity 0.35s',
        transform: visible ? 'translateY(0)' : 'translateY(8px)',
        opacity: visible ? 1 : 0,
      }}
    >
      <Badge domain={key}>{domain.label}</Badge>
      <div style={{ fontSize: 13, color: 'var(--tawn-text-2)', fontFamily: 'var(--tawn-font-mono)' }}>{domain.name}</div>
    </div>
  )
}

function FadeIn({ children, delay = 0, style }: { children: React.ReactNode; delay?: number; style?: React.CSSProperties }) {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay)
    return () => clearTimeout(t)
  }, [delay])
  return (
    <div style={{ transition: 'opacity 0.4s, transform 0.4s', opacity: visible ? 1 : 0, transform: visible ? 'translateY(0)' : 'translateY(10px)', ...style }}>
      {children}
    </div>
  )
}

export default function Dashboard() {
  const { report } = useErrors()
  const reportError = (e: unknown) => report(e instanceof Error ? e.message : String(e))
  const navigate = useNavigate()
  const mobile = useIsMobile()
  const [domains, setDomains] = useState<DomainRow[]>([])
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [notes, setNotes] = useState<PersonalNote[]>([])
  const [initialized, setInitialized] = useState(false)
  const [loading, setLoading] = useState(true)
  const [agentCount, setAgentCount] = useState<number | null>(null)
  const [chunkCount, setChunkCount] = useState<number | null>(null)

  useEffect(() => {
    Promise.all([
      getStatus().then((s) => setInitialized(s.initialized)).catch(reportError),
      getDomains().then(setDomains).catch(reportError),
      getAudit(8).then((p) => setAudit(p.entries)).catch(reportError),
      getNotes({ limit: 4 }).then((p) => setNotes(p.notes)).catch(reportError),
      fetch('/api/federation/sources').then((r) => r.json()).then((s: unknown[]) => setAgentCount(s.length)).catch(reportError),
      getChunkStats().then((s) => setChunkCount(s.total)).catch(reportError),
    ]).finally(() => setLoading(false))
  }, [])

  const enabledDomains = domains.filter((d) => d.nav)

  return (
    <>
      <style>{`
        @keyframes tawn-pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        @keyframes tawn-slide-in { from{opacity:0;transform:translateY(12px)} to{opacity:1;transform:none} }
      `}</style>
      <div style={{ maxWidth: 1040, margin: '0 auto', padding: mobile ? '24px 16px 48px' : '32px 24px 64px' }}>

        {/* heading */}
        <FadeIn delay={0}>
          <div style={{ marginBottom: mobile ? 20 : 28 }}>
            <h1 style={{ fontFamily: 'var(--tawn-font-display)', fontWeight: 700, fontSize: mobile ? 22 : 26, letterSpacing: '-0.02em', marginBottom: 4 }}>
              your twin
            </h1>
            <p style={{ color: 'var(--tawn-text-2)', fontSize: 13 }}>
              {loading ? (
                <span style={{ animation: 'tawn-pulse 1.4s ease-in-out infinite', display: 'inline-block' }}>loading…</span>
              ) : initialized ? (
                'all systems local · 127.0.0.1'
              ) : (
                <span>
                  not initialised — <span style={{ color: 'var(--tawn-lapis)', cursor: 'pointer' }} onClick={() => navigate('/setup')}>run setup →</span>
                </span>
              )}
            </p>
          </div>
        </FadeIn>

        {/* stat row */}
        <FadeIn delay={60}>
          <div style={{ display: 'grid', gridTemplateColumns: mobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: mobile ? 10 : 14, marginBottom: mobile ? 24 : 32 }}>
            <StatCard label="domains" value={loading ? '—' : enabledDomains.length || '0'} sublabel="enabled and tracking" />
            <StatCard label="context" value="local" sublabel="127.0.0.1 only, always" />
            <div style={{ cursor: 'pointer' }} onClick={() => navigate('/agents')}>
              <StatCard label="agents" value={agentCount === null ? '—' : String(agentCount)} sublabel="federated sources" />
            </div>
            <div style={{ cursor: 'pointer' }} onClick={() => navigate('/memory')}>
              <StatCard label="memory" value={chunkCount === null ? '—' : String(chunkCount)} sublabel="chunks indexed" />
            </div>
          </div>
        </FadeIn>

        {/* domain tiles */}
        {!loading && enabledDomains.length > 0 && (
          <FadeIn delay={120} style={{ marginBottom: mobile ? 24 : 32 }}>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>domains</h2>
            <div style={{ display: 'grid', gridTemplateColumns: mobile ? '1fr 1fr' : 'repeat(auto-fit, minmax(200px, 1fr))', gap: mobile ? 10 : 14 }}>
              {enabledDomains.map((d, i) => (
                <DomainTile key={d.name} domain={d} delay={i * 50} onClick={() => navigate(`/domain/${d.name}`)} />
              ))}
            </div>
          </FadeIn>
        )}

        {/* no domains nudge */}
        {!loading && enabledDomains.length === 0 && (
          <FadeIn delay={120} style={{ marginBottom: mobile ? 24 : 32 }}>
            <Card style={{ borderStyle: 'dashed' }}>
              <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', lineHeight: 1.6, marginBottom: 12 }}>
                No domains enabled yet. Create one to start tracking your context across work, wealth, research, and academic life.
              </p>
              <Button variant="secondary" size="sm" onClick={() => navigate('/domain/create')}>+ create a domain</Button>
            </Card>
          </FadeIn>
        )}

        {/* your notes — what you told the twin yourself */}
        <FadeIn delay={160}>
          <Card style={{ marginBottom: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
              <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>your notes</h2>
              <span style={{ fontSize: 12, color: 'var(--tawn-lapis)', cursor: 'pointer' }} onClick={() => navigate('/notes')}>
                {notes.length > 0 ? 'review & edit →' : 'write one →'}
              </span>
            </div>
            {notes.length > 0 ? (
              notes.map((n) => (
                <div
                  key={n.id}
                  onClick={() => navigate('/notes')}
                  style={{ padding: '9px 0', borderBottom: '1px solid var(--tawn-line)', cursor: 'pointer' }}
                >
                  <div style={{ fontSize: 13, color: 'var(--tawn-text)', lineHeight: 1.55, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                    {n.body}
                  </div>
                  <div style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', marginTop: 3 }}>
                    {n.domain ? `${n.domain} · ` : ''}{n.asof ? new Date(n.asof).toLocaleDateString() : ''}
                  </div>
                </div>
              ))
            ) : (
              <p style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>
                Nothing written yet. Notes are what you tell your twin directly — they compile into memory alongside everything it gathers.
              </p>
            )}
          </Card>
        </FadeIn>

        {/* bottom grid */}
        <FadeIn delay={180}>
          <div style={{ display: 'grid', gridTemplateColumns: mobile ? '1fr' : '1.4fr 1fr', gap: mobile ? 14 : 20, alignItems: 'start' }}>
            {/* recent activity */}
            <Card>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
                <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>recent activity</h2>
                <span style={{ fontSize: 12, color: 'var(--tawn-lapis)', cursor: 'pointer' }} onClick={() => navigate('/audit')}>full log →</span>
              </div>
              {loading ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {[1, 2, 3].map((i) => (
                    <div key={i} style={{ height: 14, borderRadius: 4, background: 'var(--tawn-line)', animation: 'tawn-pulse 1.4s ease-in-out infinite', animationDelay: `${i * 0.15}s` }} />
                  ))}
                </div>
              ) : audit.length > 0 ? (
                <Table
                  columns={['time', 'op', 'target', 'ok']}
                  rows={audit.slice(0, 6).map((e) => [
                    <span style={{ fontFamily: 'var(--tawn-font-mono)', fontSize: 11 }}>{e.ts.slice(11, 19)}</span>,
                    <span style={{ fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-lapis)' }}>{e.op}</span>,
                    <span style={{ fontFamily: 'var(--tawn-font-mono)', fontSize: 11, color: 'var(--tawn-text-2)', display: 'block', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.target}</span>,
                    <span style={{ color: e.ok ? 'var(--tawn-good)' : 'var(--tawn-crit)', fontFamily: 'var(--tawn-font-mono)', fontSize: 12 }}>{e.ok ? '✓' : '✗'}</span>,
                  ])}
                />
              ) : (
                <p style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>no activity yet</p>
              )}
            </Card>

            {/* quick actions */}
            <Card>
              <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>quick actions</h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: mobile ? 10 : 8 }}>
                <Button variant="secondary" style={{ justifyContent: 'flex-start' }} onClick={() => navigate('/chat')}>talk to your twin</Button>
                <Button variant="secondary" style={{ justifyContent: 'flex-start' }} onClick={() => navigate('/memory')}>write a note</Button>
                <Button variant="secondary" style={{ justifyContent: 'flex-start' }} onClick={() => navigate('/domain/create')}>+ track a new domain</Button>
                <Button variant="secondary" style={{ justifyContent: 'flex-start' }} onClick={() => navigate('/agents')}>connect an agent</Button>
                <Button variant="secondary" style={{ justifyContent: 'flex-start' }} onClick={() => navigate('/settings')}>review grants</Button>
              </div>
            </Card>
          </div>
        </FadeIn>
      </div>
    </>
  )
}
