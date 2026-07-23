import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { NavBar, Button, Badge, Logo, ThemeToggle } from '../ds'

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

const DOMAIN_COPY = [
  { key: 'work' as const, label: 'work', desc: "Shipped decisions, standups, project state — the maker's domain." },
  { key: 'wealth' as const, label: 'wealth', desc: 'Holdings, runway, read-only by constitution.' },
  { key: 'research' as const, label: 'research', desc: 'Papers, proposals, the thread between them.' },
  { key: 'academic' as const, label: 'academic', desc: "Coursework, advisors, the PhD your work can't see yet." },
]

const FAILURES = [
  { title: 'contextual', body: "Doesn't know who you are or what you're working on. Every session starts from zero." },
  { title: 'knowledge', body: "Doesn't know what you know. Your decisions, research, and history are invisible." },
  { title: 'operational', body: "Doesn't know what it — or another agent — just did. No shared state across tools." },
]

const GRAPH_NODES = [
  { key: 'work', angle: -55 },
  { key: 'wealth', angle: 35 },
  { key: 'research', angle: 145 },
  { key: 'academic', angle: 235 },
]

const INSTALL_METHODS = [
  {
    label: 'pip',
    cmd: 'pip install tawn && tawn init',
    note: 'Python 3.11+',
  },
  {
    label: 'uv',
    cmd: 'uv tool install tawn && tawn init',
    note: 'Recommended',
  },
  {
    label: 'clone',
    cmd: 'git clone https://github.com/tawn-hq/tawn\ncd tawn && uv sync && uv run tawn init',
    note: 'Dev mode',
  },
]

const HOW_IT_WORKS = [
  { step: '01', title: 'install', body: 'Run tawn init to scaffold ~/.tawn — your private canonical store. Nothing leaves 127.0.0.1.' },
  { step: '02', title: 'connect', body: 'Add Tawn as an MCP server in Claude Code, Cursor, or any agent that reads MCP configs.' },
  { step: '03', title: 'federate', body: 'Point Tawn at your conversation exports from Claude.ai, ChatGPT, or Gemini. It ingests and indexes them.' },
  { step: '04', title: 'recall', body: 'Ask your twin anything. It searches across all four domains and returns what you actually know.' },
]

function Kicker({ children }: { children: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center', marginBottom: 22 }}>
      <span style={{ width: 14, height: 2, background: 'var(--tawn-lapis)', display: 'inline-block' }} />
      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'var(--tawn-font-mono)' }}>{children}</span>
      <span style={{ width: 14, height: 2, background: 'var(--tawn-lapis)', display: 'inline-block' }} />
    </div>
  )
}

function EntityGraph({ size }: { size: number }) {
  const c = size / 2, r = size * 0.34, node = size * 0.05
  const pts = GRAPH_NODES.map((n) => {
    const rad = (n.angle * Math.PI) / 180
    return { ...n, x: c + r * Math.cos(rad), y: c + r * Math.sin(rad) }
  })
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: 'block' }}>
      {pts.map((p) => (
        <line key={'l' + p.key} x1={c} y1={c} x2={p.x} y2={p.y} stroke="var(--tawn-line-strong)" strokeWidth="1.5" />
      ))}
      {pts.map((p) => (
        <g key={p.key}>
          <circle cx={p.x} cy={p.y} r={node} fill="var(--tawn-surface)" stroke={`var(--tawn-${p.key})`} strokeWidth="2" />
          <text x={p.x} y={p.y + node + 16} textAnchor="middle" fontFamily="var(--tawn-font-mono)" fontSize="11" fill="var(--tawn-text-2)">{p.key}</text>
        </g>
      ))}
      <circle cx={c} cy={c} r={node * 1.6} fill="var(--tawn-lapis)" />
      <circle cx={c} cy={c} r={node * 1.6} fill="none" stroke="var(--tawn-lapis-soft)" strokeWidth="8" opacity="0.4" />
    </svg>
  )
}

function InstallTabs() {
  const [active, setActive] = useState(0)
  const [copied, setCopied] = useState(false)
  const method = INSTALL_METHODS[active]

  function copy() {
    navigator.clipboard?.writeText(method.cmd).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div style={{ background: 'var(--tawn-raised)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', overflow: 'hidden' }}>
      {/* tab strip */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--tawn-line)', background: 'var(--tawn-surface)' }}>
        {INSTALL_METHODS.map((m, i) => (
          <button
            key={m.label}
            onClick={() => setActive(i)}
            style={{ padding: '8px 16px', fontSize: 12, fontWeight: 600, fontFamily: 'var(--tawn-font-mono)', border: 'none', cursor: 'pointer', borderBottom: active === i ? '2px solid var(--tawn-lapis)' : '2px solid transparent', color: active === i ? 'var(--tawn-lapis)' : 'var(--tawn-text-2)', background: 'transparent', transition: 'color 0.15s' }}
          >
            {m.label}
          </button>
        ))}
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 11, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)', alignSelf: 'center', paddingRight: 12 }}>{method.note}</span>
      </div>
      {/* code */}
      <div style={{ position: 'relative', padding: '16px 20px' }}>
        <pre style={{ fontFamily: 'var(--tawn-font-mono)', fontSize: 13, color: 'var(--tawn-text)', whiteSpace: 'pre-wrap', lineHeight: 1.7, margin: 0 }}>{method.cmd}</pre>
        <button
          onClick={copy}
          style={{ position: 'absolute', top: 12, right: 12, fontSize: 11, fontFamily: 'var(--tawn-font-mono)', padding: '4px 10px', border: '1px solid var(--tawn-line)', borderRadius: 6, background: 'var(--tawn-surface)', color: copied ? 'var(--tawn-good)' : 'var(--tawn-text-2)', cursor: 'pointer' }}
        >
          {copied ? 'copied!' : 'copy'}
        </button>
      </div>
    </div>
  )
}

export default function Home() {
  const navigate = useNavigate()
  const mobile = useIsMobile()
  const onEnter = () => navigate('/dashboard')

  return (
    <div style={{ background: 'var(--tawn-bg)', minHeight: '100vh' }}>
      <NavBar
        links={mobile ? [] : [
          { label: 'vision', to: '#vision' },
          { label: 'how it works', to: '#how' },
          { label: 'install', to: '#install' },
        ]}
        right={<div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><ThemeToggle /><Button size="sm" onClick={onEnter}>open tawn</Button></div>}
      />

      {/* ── Hero ── */}
      <section id="vision" style={{ maxWidth: 1040, margin: '0 auto', padding: mobile ? '48px 20px 40px' : '88px 24px 64px', display: 'grid', gridTemplateColumns: mobile ? '1fr' : '1.1fr 0.9fr', gap: mobile ? 32 : 24, alignItems: 'center' }}>
        <div style={{ textAlign: mobile ? 'center' : 'left' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: '1px solid var(--tawn-line)', borderRadius: 999, padding: '5px 12px 5px 8px', marginBottom: 22, background: 'var(--tawn-surface)' }}>
            <Logo size={16} withWordmark={false} />
            <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-2)' }}>the twin you own</span>
          </div>
          <h1 style={{ fontFamily: 'var(--tawn-font-display)', fontWeight: 700, fontSize: mobile ? 34 : 50, letterSpacing: '-0.03em', color: 'var(--tawn-text)', lineHeight: 1.06 }}>
            one brain.<br />every agent shares it.
          </h1>
          <p style={{ fontSize: mobile ? 15 : 17, color: 'var(--tawn-text-2)', marginTop: 20, lineHeight: 1.6, maxWidth: 460, marginLeft: mobile ? 'auto' : 0, marginRight: mobile ? 'auto' : 0 }}>
            Tawn is a local-first personal twin — a context core for your whole life that every AI tool reads from and writes back to. Work, wealth, research, academic. One place.
          </p>
          <div style={{ display: 'flex', gap: 12, justifyContent: mobile ? 'center' : 'flex-start', marginTop: 30, flexWrap: 'wrap' }}>
            <Button size="lg" onClick={onEnter}>open tawn</Button>
            <Button size="lg" variant="secondary" onClick={() => document.getElementById('install')?.scrollIntoView({ behavior: 'smooth' })}>get started</Button>
          </div>
          <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginTop: 20, fontFamily: 'var(--tawn-font-mono)' }}>
            local-first · 127.0.0.1 only · never spends without a human gate
          </p>
        </div>
        {!mobile && (
          <div style={{ border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', background: 'var(--tawn-surface)', padding: 24, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <EntityGraph size={260} />
          </div>
        )}
      </section>

      {/* ── Three failures ── */}
      <section style={{ borderTop: '1px solid var(--tawn-line)', background: 'var(--tawn-raised)' }}>
        <div style={{ maxWidth: 960, margin: '0 auto', padding: mobile ? '44px 20px' : '64px 24px' }}>
          <Kicker>three ways ai memory fails</Kicker>
          <div style={{ display: 'grid', gridTemplateColumns: mobile ? '1fr' : 'repeat(3, 1fr)', gap: 16 }}>
            {FAILURES.map((f) => (
              <div key={f.title} style={{ background: 'var(--tawn-surface)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', padding: '20px 22px' }}>
                <div style={{ fontFamily: 'var(--tawn-font-mono)', fontSize: 13, color: 'var(--tawn-lapis)', marginBottom: 8 }}>{f.title}</div>
                <div style={{ fontSize: 14, color: 'var(--tawn-text)', lineHeight: 1.55 }}>{f.body}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section id="how" style={{ maxWidth: 960, margin: '0 auto', padding: mobile ? '44px 20px' : '72px 24px' }}>
        <Kicker>how it works</Kicker>
        <div style={{ display: 'grid', gridTemplateColumns: mobile ? '1fr' : 'repeat(4, 1fr)', gap: 20 }}>
          {HOW_IT_WORKS.map((s) => (
            <div key={s.step}>
              <div style={{ fontFamily: 'var(--tawn-font-mono)', fontSize: 11, color: 'var(--tawn-lapis)', fontWeight: 600, marginBottom: 10, letterSpacing: '0.06em' }}>{s.step}</div>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, fontFamily: 'var(--tawn-font-display)' }}>{s.title}</div>
              <div style={{ fontSize: 13, color: 'var(--tawn-text-2)', lineHeight: 1.6 }}>{s.body}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Domains ── */}
      <section style={{ borderTop: '1px solid var(--tawn-line)', background: 'var(--tawn-raised)' }}>
        <div style={{ maxWidth: 960, margin: '0 auto', padding: mobile ? '44px 20px' : '64px 24px' }}>
          <Kicker>four domains, one entity graph</Kicker>
          <div style={{ display: 'grid', gridTemplateColumns: mobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: 16 }}>
            {DOMAIN_COPY.map((d) => (
              <div key={d.key} style={{ border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', padding: '18px 18px', background: 'var(--tawn-surface)' }}>
                <Badge domain={d.key}>{d.label}</Badge>
                <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginTop: 12, lineHeight: 1.55 }}>{d.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Install ── */}
      <section id="install" style={{ maxWidth: 720, margin: '0 auto', padding: mobile ? '44px 20px' : '72px 24px' }}>
        <Kicker>install tawn</Kicker>
        <p style={{ fontSize: 15, color: 'var(--tawn-text-2)', lineHeight: 1.6, textAlign: 'center', marginBottom: 28 }}>
          Requires Python 3.11+ and PostgreSQL. Ollama optional (adds local model support).
        </p>
        <InstallTabs />
        <div style={{ marginTop: 20, display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'center' }}>
          <Button variant="secondary" size="sm" onClick={() => navigate('/setup')}>run setup wizard →</Button>
          <a href="https://github.com/tawn-ai/tawn" target="_blank" rel="noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600, color: 'var(--tawn-text-2)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', padding: '8px 18px', background: 'var(--tawn-raised)', textDecoration: 'none' }}>
            view on GitHub
          </a>
        </div>
      </section>

      {/* ── CTA ── */}
      <section style={{ borderTop: '1px solid var(--tawn-line)', background: 'var(--tawn-raised)' }}>
        <div style={{ maxWidth: 600, margin: '0 auto', padding: mobile ? '48px 20px' : '72px 24px', textAlign: 'center' }}>
          <h2 style={{ fontFamily: 'var(--tawn-font-display)', fontWeight: 700, fontSize: mobile ? 26 : 34, letterSpacing: '-0.02em', marginBottom: 14 }}>own your context.</h2>
          <p style={{ fontSize: 15, color: 'var(--tawn-text-2)', lineHeight: 1.6, marginBottom: 28 }}>Install takes two minutes. Your twin is ready to query by the end of the first compile.</p>
          <Button size="lg" onClick={onEnter}>open tawn →</Button>
        </div>
      </section>

      <footer style={{ borderTop: '1px solid var(--tawn-line)', padding: '24px', textAlign: 'center', fontSize: 12, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)', display: 'flex', flexWrap: 'wrap', gap: 16, justifyContent: 'center', alignItems: 'center' }}>
        <span>tawn</span>
        <a href="https://github.com/tawn-ai/tawn" target="_blank" rel="noreferrer" style={{ color: 'var(--tawn-text-3)', textDecoration: 'none' }}>github</a>
        <a href="https://github.com/tawn-ai/tawn/issues" target="_blank" rel="noreferrer" style={{ color: 'var(--tawn-text-3)', textDecoration: 'none' }}>issues</a>
        <span>read-only on money, always</span>
      </footer>
    </div>
  )
}
