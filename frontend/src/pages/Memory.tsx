import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { marked } from 'marked'
import AppNav from '../components/AppNav'
import { Card, Input, Textarea, Button, Badge } from '../ds'
import { postNote, postRecall, postCompile, getChunks, type RecallResult, type SnippetChunk, type FeedChunk } from '../lib/api'

marked.setOptions({ breaks: true })

function Md({ src, maxLen }: { src: string; maxLen?: number }) {
  const html = useMemo(() => {
    const text = maxLen && src.length > maxLen ? src.slice(0, maxLen) + '…' : src
    return marked.parse(text) as string
  }, [src, maxLen])
  return (
    <div
      className="tawn-md"
      dangerouslySetInnerHTML={{ __html: html }}
      style={{ fontSize: 14, color: 'var(--tawn-text)', lineHeight: 1.65 }}
    />
  )
}

const DOMAIN_ANGLE: Record<string, number> = { work: -135, wealth: -45, research: 45, academic: 135 }

const DOMAINS = ['work', 'wealth', 'research', 'academic', 'hobby'] as const
type Domain = typeof DOMAINS[number]

function ViewToggle({ view, setView }: { view: 'feed' | 'graph'; setView: (v: 'feed' | 'graph') => void }) {
  const opt = (v: 'feed' | 'graph', label: string) => (
    <span
      key={v}
      onClick={() => setView(v)}
      style={{ cursor: 'pointer', padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'var(--tawn-font-mono)', borderRadius: 999, color: view === v ? 'var(--tawn-lapis)' : 'var(--tawn-text-2)', background: view === v ? 'var(--tawn-lapis-soft)' : 'transparent' }}
    >
      {label}
    </span>
  )
  return (
    <div style={{ display: 'inline-flex', gap: 2, border: '1px solid var(--tawn-line)', borderRadius: 999, padding: 3 }}>
      {opt('feed', 'feed')}
      {opt('graph', 'graph')}
    </div>
  )
}

function SourceTypeBadge({ type }: { type: FeedChunk['source_type'] }) {
  const map: Record<string, string> = {
    'agent-memory': 'var(--tawn-lapis)',
    history: 'var(--tawn-text-3)',
    raw: 'var(--tawn-text-3)',
    imports: 'var(--tawn-warn)',
    external: 'var(--tawn-text-3)',
  }
  const color = map[type] || 'var(--tawn-text-3)'
  return (
    <span style={{ fontSize: 10, fontFamily: 'var(--tawn-font-mono)', border: `1px solid ${color}`, color, borderRadius: 999, padding: '1px 6px' }}>{type}</span>
  )
}

function FeedCard({ chunk, onClick }: { chunk: FeedChunk; onClick: () => void }) {
  const [hover, setHover] = useState(false)
  const dom = DOMAINS.includes(chunk.domain as Domain) ? chunk.domain as Domain : undefined
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ borderBottom: '1px solid var(--tawn-line)', cursor: 'pointer', background: hover ? 'var(--tawn-lapis-soft)' : 'transparent', margin: '0 -20px', padding: '14px 20px', transition: 'background 0.1s' }}
    >
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 7, flexWrap: 'wrap' }}>
        {dom && <Badge domain={dom}>{dom}</Badge>}
        {chunk.stale && <Badge status="warn">stale</Badge>}
        <SourceTypeBadge type={chunk.source_type} />
        <span style={{ fontSize: 11, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{chunk.source_label}</span>
        <span style={{ fontSize: 11, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)', whiteSpace: 'nowrap' }}>
          {chunk.compiled_at ? new Date(chunk.compiled_at).toLocaleDateString() : ''}
        </span>
      </div>
      <Md src={chunk.content} maxLen={300} />
    </div>
  )
}

function RecallCard({ c, onClick }: { c: SnippetChunk; onClick?: () => void }) {
  const dom = DOMAINS.includes(c.domain as Domain) ? c.domain as Domain : undefined
  return (
    <div
      onClick={onClick}
      style={{ padding: '14px 0', borderBottom: '1px solid var(--tawn-line)', cursor: onClick ? 'pointer' : 'default' }}
    >
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
        {dom && <Badge domain={dom}>{dom}</Badge>}
        {c.stale && <Badge status="warn">stale</Badge>}
        <span style={{ fontSize: 11, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>{c.source}</span>
        {c.score !== null && <span style={{ fontSize: 11, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)', marginLeft: 'auto' }}>score {c.score.toFixed(2)}</span>}
      </div>
      <Md src={c.content} maxLen={500} />
    </div>
  )
}

function MemoryGraph({ size }: { size: number }) {
  const c = size / 2, r1 = size * 0.3
  const domainPos: Record<string, { x: number; y: number }> = {}
  Object.entries(DOMAIN_ANGLE).forEach(([d, angle]) => {
    const rad = (angle * Math.PI) / 180
    domainPos[d] = { x: c + r1 * Math.cos(rad), y: c + r1 * Math.sin(rad) }
  })
  return (
    <svg width="100%" height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: 'block' }}>
      {Object.entries(domainPos).map(([d, p]) => (
        <line key={'r' + d} x1={c} y1={c} x2={p.x} y2={p.y} stroke="var(--tawn-line-strong)" strokeWidth="1.5" />
      ))}
      {Object.entries(domainPos).map(([d, p]) => (
        <g key={d}>
          <circle cx={p.x} cy={p.y} r={size * 0.035} fill="var(--tawn-surface)" stroke={`var(--tawn-${d})`} strokeWidth="2.5" />
          <text x={p.x} y={p.y + size * 0.035 + 16} textAnchor="middle" fontFamily="var(--tawn-font-mono)" fontWeight="600" fontSize={size * 0.026} fill="var(--tawn-text)">{d}</text>
        </g>
      ))}
      <circle cx={c} cy={c} r={size * 0.014} fill="var(--tawn-lapis-soft)" />
      <circle cx={c} cy={c} r={size * 0.028} fill="var(--tawn-lapis)" />
    </svg>
  )
}

export default function Memory() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [view, setView] = useState<'feed' | 'graph'>('feed')
  const [domainFilter, setDomainFilter] = useState<string>('')
  const [sourceTypeFilter, setSourceTypeFilter] = useState<string>('knowledge')
  const [result, setResult] = useState<RecallResult | null>(null)
  const [recallStatus, setRecallStatus] = useState('')
  const [noteText, setNoteText] = useState('')
  const [noteDomain, setNoteDomain] = useState('')
  const [noteStatus, setNoteStatus] = useState('')
  const [compileStatus, setCompileStatus] = useState('')
  const [attached, setAttached] = useState<File | null>(null)
  const [feedChunks, setFeedChunks] = useState<FeedChunk[]>([])
  const [feedTotal, setFeedTotal] = useState(0)
  const [feedOffset, setFeedOffset] = useState(0)
  const [feedLoading, setFeedLoading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const LIMIT = 20

  function loadFeed(offset = 0, domain = domainFilter, srcType = sourceTypeFilter) {
    setFeedLoading(true)
    getChunks({ domain: domain || undefined, source_type: srcType || undefined, limit: LIMIT, offset })
      .then((page) => { setFeedChunks(page.chunks); setFeedTotal(page.total); setFeedOffset(offset) })
      .catch(() => {})
      .finally(() => setFeedLoading(false))
  }

  useEffect(() => { loadFeed(0, domainFilter, sourceTypeFilter) }, [domainFilter, sourceTypeFilter])

  async function handleRecall(e: FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    setRecallStatus('searching…')
    setResult(null)
    try {
      const res = await postRecall(query.trim())
      setResult(res)
      const count = res.chunks?.length ?? 0
      setRecallStatus(res.format === 'composed' ? 'composed answer' : count ? `${count} result${count !== 1 ? 's' : ''}` : 'no results')
    } catch (err: unknown) {
      setRecallStatus(`error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  async function handleNote(e: FormEvent) {
    e.preventDefault()
    if (!noteText.trim()) return
    setNoteStatus('saving…')
    try {
      const res = await postNote(noteText.trim(), noteDomain.trim() || undefined)
      setNoteStatus(`saved → ${res.path}`)
      setNoteText('')
      setNoteDomain('')
      setAttached(null)
    } catch (err: unknown) {
      setNoteStatus(`error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  async function handleCompile() {
    setCompileStatus('compiling…')
    try {
      const res = await postCompile()
      setCompileStatus(res.ok
        ? `done — ${res.files_processed} files · +${res.chunks_added}/-${res.chunks_removed} chunks · ${res.entities_resolved} entities`
        : `failed: ${res.error}`)
      if (res.ok) loadFeed(0)
    } catch (err: unknown) {
      setCompileStatus(`error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  const recallChunks = result?.chunks ?? []
  const hasResult = !!result

  return (
    <div style={{ background: 'var(--tawn-bg)', minHeight: '100vh' }}>
      <AppNav />
      <div style={{ maxWidth: 760, margin: '0 auto', padding: '32px 24px 64px' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>memory</h1>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginBottom: 20 }}>everything your twin has recalled, been told, and watched happen — one feed, every domain.</p>

        <form onSubmit={handleRecall} style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder='search your whole memory — "what did I decide about…"' style={{ flex: 1 }} />
          <Button type="submit">recall</Button>
          {result && <Button variant="secondary" onClick={() => { setResult(null); setRecallStatus('') }}>clear</Button>}
        </form>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <ViewToggle view={view} setView={setView} />
            {!hasResult && view === 'feed' && (
              <>
                <select
                  value={sourceTypeFilter}
                  onChange={(e) => setSourceTypeFilter(e.target.value)}
                  style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', padding: '5px 8px', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', background: 'var(--tawn-raised)', color: 'var(--tawn-text)' }}
                >
                  <option value="knowledge">knowledge</option>
                  <option value="all">all</option>
                  <option value="imports">imports</option>
                </select>
                <select
                  value={domainFilter}
                  onChange={(e) => setDomainFilter(e.target.value)}
                  style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', padding: '5px 8px', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', background: 'var(--tawn-raised)', color: 'var(--tawn-text)' }}
                >
                  <option value="">all domains</option>
                  {DOMAINS.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </>
            )}
          </div>
          {recallStatus && <span style={{ fontSize: 11, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>{recallStatus}</span>}
        </div>

        <Card padded={false} style={{ marginBottom: 24 }}>
          {view === 'feed' ? (
            <div style={{ padding: '0 20px' }}>
              {hasResult ? (
                <>
                  {result?.format === 'composed' && result.answer && (
                    <div style={{ padding: '16px 0', borderBottom: '1px solid var(--tawn-line)', fontSize: 14, color: 'var(--tawn-text)', lineHeight: 1.6 }}>{result.answer}</div>
                  )}
                  {recallChunks.length > 0
                    ? recallChunks.map((c, i) => (
                        <RecallCard key={i} c={c} onClick={c.id ? () => navigate(`/memory/chunk/${c.id}`) : undefined} />
                      ))
                    : <div style={{ padding: '24px 0', fontSize: 13, color: 'var(--tawn-text-2)', textAlign: 'center' }}>nothing recalled for that yet.</div>}
                </>
              ) : feedLoading ? (
                <div style={{ padding: '24px 0', fontSize: 13, color: 'var(--tawn-text-2)', textAlign: 'center' }}>loading…</div>
              ) : feedChunks.length > 0 ? (
                <>
                  {feedChunks.map((c) => (
                    <FeedCard key={c.id} chunk={c} onClick={() => navigate(`/memory/chunk/${c.id}`)} />
                  ))}
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'center', padding: '14px 0' }}>
                    {feedOffset > 0 && (
                      <Button variant="secondary" size="sm" onClick={() => loadFeed(feedOffset - LIMIT)}>← prev</Button>
                    )}
                    <span style={{ fontSize: 12, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)', alignSelf: 'center' }}>
                      {feedOffset + 1}–{Math.min(feedOffset + LIMIT, feedTotal)} of {feedTotal}
                    </span>
                    {feedOffset + LIMIT < feedTotal && (
                      <Button variant="secondary" size="sm" onClick={() => loadFeed(feedOffset + LIMIT)}>next →</Button>
                    )}
                  </div>
                </>
              ) : (
                <div style={{ padding: '24px 0', fontSize: 13, color: 'var(--tawn-text-2)', textAlign: 'center' }}>
                  nothing compiled yet — write a note or run compile below.
                </div>
              )}
              <div style={{ height: 4 }} />
            </div>
          ) : (
            <div style={{ padding: '20px 8px' }}>
              <MemoryGraph size={480} />
              <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', textAlign: 'center', marginTop: 4, fontFamily: 'var(--tawn-font-mono)' }}>entity graph — domain connections</p>
            </div>
          )}
        </Card>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <Card>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>write a note</div>
            <form onSubmit={handleNote}>
              <Textarea rows={3} placeholder="What do you want to remember?" value={noteText} onChange={(e) => setNoteText(e.target.value)} />
              <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <Input placeholder="domain (optional)" value={noteDomain} onChange={(e) => setNoteDomain(e.target.value)} style={{ flex: 1, minWidth: 120 }} />
                <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={(e) => setAttached(e.target.files?.[0] || null)} />
                <Button type="button" variant="secondary" onClick={() => fileRef.current?.click()}>attach</Button>
                <Button type="submit">save</Button>
              </div>
            </form>
            {attached && (
              <div style={{ marginTop: 10 }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-2)', background: 'var(--tawn-raised)', border: '1px solid var(--tawn-line)', borderRadius: 8, padding: '5px 10px' }}>
                  {attached.name}
                  <span onClick={() => setAttached(null)} style={{ color: 'var(--tawn-crit)', cursor: 'pointer' }}>remove</span>
                </span>
              </div>
            )}
            {noteStatus && <p style={{ fontSize: 12, color: 'var(--tawn-text-2)', marginTop: 8, fontFamily: 'var(--tawn-font-mono)' }}>{noteStatus}</p>}
          </Card>
          <Card>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>compile</div>
            <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', lineHeight: 1.5, marginBottom: 12 }}>
              Re-index raw/, granted read paths, and chat history into searchable chunks.
            </p>
            <Button variant="secondary" onClick={handleCompile}>run compile</Button>
            {compileStatus && <p style={{ fontSize: 12, color: 'var(--tawn-text-2)', marginTop: 8, fontFamily: 'var(--tawn-font-mono)' }}>{compileStatus}</p>}
          </Card>
        </div>
      </div>
    </div>
  )
}
