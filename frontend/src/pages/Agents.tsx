import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Button, Badge } from '../ds'
import { useErrors } from '../components/Errors'

interface FedSource { name: string; path: string; domain: string | null; adapter: string | null }
interface ConvMeta { id: number; source: string; source_path: string; project: string | null; domain: string | null; ingested_at: string | null }

function PromptModal({ onConfirm, onCancel }: { onConfirm: (v: string) => void; onCancel: () => void }) {
  const [val, setVal] = useState('')
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: 'var(--tawn-bg)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-lg)', padding: '28px 28px 24px', maxWidth: 440, width: '90vw', boxShadow: '0 12px 40px rgba(0,0,0,0.3)' }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>add federation source</h3>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginBottom: 16, lineHeight: 1.5 }}>
          Enter a path or glob to watch (e.g. <code style={{ fontFamily: 'var(--tawn-font-mono)' }}>~/Downloads/claude-export.json</code>)
        </p>
        <input
          autoFocus value={val} onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && val.trim()) onConfirm(val.trim()); if (e.key === 'Escape') onCancel() }}
          placeholder="~/Downloads/export.json"
          style={{ width: '100%', boxSizing: 'border-box', fontFamily: 'var(--tawn-font-mono)', fontSize: 13, padding: '9px 12px', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', background: 'var(--tawn-raised)', color: 'var(--tawn-text)', marginBottom: 16, outline: 'none' }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button onClick={onCancel} style={{ fontSize: 13, padding: '7px 16px', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', background: 'transparent', color: 'var(--tawn-text-2)', cursor: 'pointer' }}>cancel</button>
          <button onClick={() => val.trim() && onConfirm(val.trim())} disabled={!val.trim()} style={{ fontSize: 13, padding: '7px 16px', border: 'none', borderRadius: 'var(--tawn-radius-sm)', background: 'var(--tawn-lapis)', color: '#fff', cursor: val.trim() ? 'pointer' : 'not-allowed', opacity: val.trim() ? 1 : 0.5 }}>add source</button>
        </div>
      </div>
    </div>
  )
}

function SourceConversations({ sourceName, onOpen }: { sourceName: string; onOpen: (id: number) => void }) {
  const [convs, setConvs] = useState<ConvMeta[] | null>(null)
  useEffect(() => {
    fetch(`/api/federation/conversations?source=${encodeURIComponent(sourceName)}&limit=200`)
      .then((r) => r.json())
      .then(setConvs)
      .catch(() => setConvs([]))
  }, [sourceName])

  if (convs === null) return <div style={{ padding: '10px 20px', fontSize: 12, color: 'var(--tawn-text-3)' }}>loading…</div>
  if (convs.length === 0) return <div style={{ padding: '10px 20px', fontSize: 12, color: 'var(--tawn-text-3)' }}>no conversations ingested yet — run federation merge</div>

  const byProject: Record<string, ConvMeta[]> = {}
  for (const c of convs) {
    const key = c.project || '(ungrouped)'
    if (!byProject[key]) byProject[key] = []
    byProject[key].push(c)
  }

  return (
    <div style={{ borderTop: '1px solid var(--tawn-line)', background: 'var(--tawn-raised)' }}>
      {Object.entries(byProject).map(([project, items]) => (
        <div key={project}>
          <div style={{ padding: '6px 20px 4px', fontSize: 10, fontWeight: 700, color: 'var(--tawn-text-3)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{project}</div>
          {items.map((c) => (
            <div
              key={c.id}
              onClick={() => onOpen(c.id)}
              style={{ padding: '8px 20px 8px 28px', cursor: 'pointer', borderBottom: '1px solid var(--tawn-line)', display: 'flex', alignItems: 'center', gap: 10 }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--tawn-lapis-soft)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <span style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {c.source_path.split('/').pop()}
              </span>
              {c.domain && <Badge tone="neutral">{c.domain}</Badge>}
              <span style={{ fontSize: 10, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)', whiteSpace: 'nowrap' }}>
                {c.ingested_at?.slice(0, 10) || ''}
              </span>
              <span style={{ fontSize: 11, color: 'var(--tawn-lapis)', fontFamily: 'var(--tawn-font-mono)' }}>view →</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

const CONNECT_SNIPPETS = [
  { name: 'Claude Code', slug: 'claude-code', desc: 'Add Tawn as an MCP server — your twin context ships with every session.' },
  { name: 'Cursor', slug: 'cursor', desc: 'Add the MCP config snippet to .cursor/mcp.json and Tawn is always in context.' },
  { name: 'Gemini CLI', slug: 'gemini-cli', desc: 'Pass the Tawn MCP endpoint in your gemini.json servers block.' },
  { name: 'Any agent', slug: 'generic', desc: 'Standard AGENTS.md block — paste into any project that reads agent instructions.' },
]

const MCP_SNIPPET = `# In your MCP config (servers block):
tawn:
  command: tawn
  args: ["mcp"]
  # connects to tawn:8787/mcp`

export default function Agents() {
  const { report } = useErrors()
  const reportError = (e: unknown) => report(e instanceof Error ? e.message : String(e))
  const navigate = useNavigate()
  const [sources, setSources] = useState<FedSource[]>([])
  const [copied, setCopied] = useState<string | null>(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set())

  useEffect(() => {
    fetch('/api/federation/sources')
      .then((r) => r.json())
      .then((data) => setSources(Array.isArray(data) ? data : []))
      .catch(reportError)
  }, [])

  function copy(text: string, slug: string) {
    navigator.clipboard?.writeText(text).catch(reportError)
    setCopied(slug)
    setTimeout(() => setCopied(null), 2000)
  }

  async function addSource(path: string) {
    setShowAddModal(false)
    await fetch('/api/federation/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    }).then(() => fetch('/api/federation/sources').then((r) => r.json()).then(setSources)).catch(reportError)
  }

  async function removeSource(name: string) {
    await fetch(`/api/federation/sources/${name}`, { method: 'DELETE' }).catch(reportError)
    setSources((s) => s.filter((x) => x.name !== name))
  }

  function toggleSource(name: string) {
    setExpandedSources((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name); else next.add(name)
      return next
    })
  }

  return (
    <>
      {showAddModal && <PromptModal onConfirm={addSource} onCancel={() => setShowAddModal(false)} />}
      <div style={{ maxWidth: 760, margin: '0 auto', padding: '32px 24px 64px' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>agents</h1>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginBottom: 28 }}>
          two flows: agents read Tawn's context via MCP · Tawn ingests agents' conversation history via federation.
        </p>

        {/* MCP status */}
        <div style={{ background: 'var(--tawn-surface)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', padding: '14px 20px', marginBottom: 28 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--tawn-good)' }} />
            <span style={{ fontSize: 13, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-2)' }}>MCP server · tawn:8787/mcp</span>
          </div>
          <p style={{ fontSize: 13, color: 'var(--tawn-text)', lineHeight: 1.5 }}>
            Agents query your twin for real-time context. Every call is logged to the audit trail.
          </p>
        </div>

        {/* Federation sources */}
        <div style={{ marginBottom: 32 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              federation sources <span style={{ color: 'var(--tawn-text-3)', fontWeight: 400 }}>— history inbound</span>
            </h2>
            <Button size="sm" variant="secondary" onClick={() => setShowAddModal(true)}>+ add source</Button>
          </div>
          {sources.length === 0 ? (
            <Card>
              <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', lineHeight: 1.5 }}>
                No sources yet. Add a path to a conversation export and Tawn will ingest it automatically.
              </p>
            </Card>
          ) : (
            <Card padded={false}>
              {sources.map((s) => (
                <div key={s.name}>
                  <div
                    style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', borderBottom: '1px solid var(--tawn-line)', cursor: 'pointer' }}
                    onClick={() => toggleSource(s.name)}
                  >
                    <span style={{ fontSize: 11, color: 'var(--tawn-text-3)', transition: 'transform 0.15s', display: 'inline-block', transform: expandedSources.has(s.name) ? 'rotate(90deg)' : 'none' }}>▶</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text)' }}>{s.path}</div>
                      <div style={{ fontSize: 11, color: 'var(--tawn-text-3)', marginTop: 2, fontFamily: 'var(--tawn-font-mono)' }}>
                        {s.adapter || 'auto'}{s.domain ? ` · ${s.domain}` : ''}
                      </div>
                    </div>
                    <Badge tone="neutral">{s.name}</Badge>
                    <span onClick={(e) => { e.stopPropagation(); removeSource(s.name) }} style={{ fontSize: 12, color: 'var(--tawn-crit)', cursor: 'pointer', fontFamily: 'var(--tawn-font-mono)' }}>remove</span>
                  </div>
                  {expandedSources.has(s.name) && (
                    <SourceConversations
                      sourceName={s.name}
                      onOpen={(id) => navigate(`/agents/conversation/${id}`)}
                    />
                  )}
                </div>
              ))}
            </Card>
          )}
        </div>

        {/* Connect snippets */}
        <div>
          <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
            connect your agents <span style={{ color: 'var(--tawn-text-3)', fontWeight: 400 }}>— context outbound</span>
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {CONNECT_SNIPPETS.map((a) => (
              <Card key={a.slug}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{a.name}</div>
                  <Badge tone="neutral">{a.slug}</Badge>
                </div>
                <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', lineHeight: 1.5, marginBottom: 12 }}>{a.desc}</p>
                <pre style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', background: 'var(--tawn-raised)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', padding: '10px 12px', overflowX: 'auto', color: 'var(--tawn-text-2)', whiteSpace: 'pre-wrap', lineHeight: 1.6, marginBottom: 10 }}>{MCP_SNIPPET}</pre>
                <Button size="sm" variant="secondary" onClick={() => copy(MCP_SNIPPET, a.slug)}>
                  {copied === a.slug ? 'copied!' : 'copy snippet'}
                </Button>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
