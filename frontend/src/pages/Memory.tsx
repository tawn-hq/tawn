import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { marked } from 'marked'
import { Card, Input, Textarea, Button, Badge } from '../ds'
import { useErrors } from '../components/Errors'
import EntityGraph from '../components/EntityGraph'
import { postNote, postRecall, postCompile, getGroups, getGroupDocument, getWikiGraph, getEnrichStatus, postEnrich, type GraphData, type EnrichStatus, type RecallResult, type SnippetChunk, type GroupCard, type GroupDocument } from '../lib/api'

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

function GroupCardView({ card, onOpen }: { card: GroupCard; onOpen: (id: number) => void }) {
  const [open, setOpen] = useState(false)
  const [doc, setDoc] = useState<GroupDocument | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const dom = DOMAINS.includes(card.domain as Domain) ? (card.domain as Domain) : undefined
  const heading = card.title || card.group_key.split('/').pop() || card.group_key

  // Chunks are the retrieval unit; the document is the reading unit. Expanding
  // reassembles the group into the whole file rather than listing fragments.
  function toggle() {
    const next = !open
    setOpen(next)
    if (next && !doc && !loading) {
      setLoading(true)
      setErr('')
      getGroupDocument(card.group_key)
        .then(setDoc)
        .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)))
        .finally(() => setLoading(false))
    }
  }

  const html = useMemo(() => (doc ? (marked.parse(doc.body) as string) : ''), [doc])

  return (
    <div style={{ border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', background: 'var(--tawn-surface)', marginBottom: 10, overflow: 'hidden' }}>
      <div
        onClick={toggle}
        style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'var(--tawn-raised)', borderBottom: (open || card.summary) ? '1px solid var(--tawn-line)' : 'none', cursor: 'pointer', flexWrap: 'wrap' }}
      >
        <span style={{ fontFamily: 'var(--tawn-font-mono)', fontSize: 11, color: 'var(--tawn-text-3)', width: 10 }}>{open ? '\u2212' : '+'}</span>
        {dom && <Badge domain={dom}>{dom}</Badge>}
        <strong style={{ fontSize: 13, color: 'var(--tawn-text)' }}>{heading}</strong>
        <span style={{ marginLeft: 'auto', fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', whiteSpace: 'nowrap' }}>
          {card.chunk_count} {card.chunk_count === 1 ? 'entry' : 'entries'}
          {card.latest_at ? ` \u00b7 ${new Date(card.latest_at).toLocaleDateString()}` : ''}
        </span>
      </div>

      {card.summary && !open && (
        <div style={{ padding: '9px 12px', fontSize: 12.5, lineHeight: 1.6, color: 'var(--tawn-text-2)' }}>
          {card.summary}
        </div>
      )}

      {open && (
        <div style={{ padding: '12px 14px' }}>
          {loading && <div style={{ fontSize: 12, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>reassembling document…</div>}
          {err && <div style={{ fontSize: 12, color: 'var(--tawn-warn)' }}>{err}</div>}
          {doc && (
            <>
              <div style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', marginBottom: 10, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <span>{doc.chunk_count} chunks reassembled</span>
                <span>{doc.enriched_chunks}/{doc.chunk_count} summarised</span>
                {doc.source_paths[0] && <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{doc.source_paths[0]}</span>}
              </div>
              <div
                className="tawn-md"
                dangerouslySetInnerHTML={{ __html: html }}
                style={{ fontSize: 13.5, lineHeight: 1.7, color: 'var(--tawn-text)', maxHeight: 620, overflowY: 'auto' }}
              />
              <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {doc.chunk_ids.slice(0, 1).map((id) => (
                  <Button key={id} variant="secondary" size="sm" onClick={() => onOpen(id)}>
                    open first chunk
                  </Button>
                ))}
              </div>
            </>
          )}
        </div>
      )}
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

export default function Memory() {
  const { report } = useErrors()
  const reportError = (e: unknown) => report(e instanceof Error ? e.message : String(e))
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [view, setView] = useState<'feed' | 'graph'>('feed')
  const [domainFilter, setDomainFilter] = useState<string>('')
  const [result, setResult] = useState<RecallResult | null>(null)
  const [recallStatus, setRecallStatus] = useState('')
  const [noteText, setNoteText] = useState('')
  const [noteDomain, setNoteDomain] = useState('')
  const [noteStatus, setNoteStatus] = useState('')
  const [compileStatus, setCompileStatus] = useState('')
  const [attached, setAttached] = useState<File | null>(null)
  const [groups, setGroups] = useState<GroupCard[]>([])
  const [feedTotal, setFeedTotal] = useState(0)
  const [feedOffset, setFeedOffset] = useState(0)
  const [feedLoading, setFeedLoading] = useState(false)
  const [graph, setGraph] = useState<GraphData>({ nodes: [], links: [] })
  const [enrich, setEnrich] = useState<EnrichStatus | null>(null)
  const [enrichBusy, setEnrichBusy] = useState(false)
  const [enrichMsg, setEnrichMsg] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const LIMIT = 20

  function loadFeed(offset = 0, domain = domainFilter) {
    setFeedLoading(true)
    getGroups({ domain: domain || undefined, limit: LIMIT, offset })
      .then((page) => { setGroups(page.groups); setFeedTotal(page.total); setFeedOffset(offset) })
      .catch(reportError)
      .finally(() => setFeedLoading(false))
  }

  useEffect(() => { loadFeed(0, domainFilter) }, [domainFilter])

  // Fetched lazily: the graph is only needed once the tab is opened.
  useEffect(() => {
    if (view === 'graph' && graph.nodes.length === 0) {
      getWikiGraph({ domain: domainFilter || undefined, limit: 250 })
        .then(setGraph)
        .catch(reportError)
    }
  }, [view, domainFilter])

  useEffect(() => { getEnrichStatus().then(setEnrich).catch(reportError) }, [])

  async function handleEnrich() {
    setEnrichBusy(true)
    setEnrichMsg('enriching…')
    try {
      const res = await postEnrich(200, true)
      setEnrichMsg(res.ok
        ? `+${res.chunks_enriched} chunks, +${res.groups_enriched} groups`
        : `stopped: ${res.error}`)
      getEnrichStatus().then(setEnrich).catch(reportError)
      loadFeed(feedOffset)
    } catch (e: unknown) {
      setEnrichMsg(`error: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setEnrichBusy(false)
    }
  }

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
    <>
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
              <select
                value={domainFilter}
                onChange={(e) => setDomainFilter(e.target.value)}
                style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', padding: '5px 8px', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', background: 'var(--tawn-raised)', color: 'var(--tawn-text)' }}
              >
                <option value="">all domains</option>
                {DOMAINS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
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
              ) : groups.length > 0 ? (
                <>
                  <div style={{ paddingTop: 14 }}>
                    {groups.map((g) => (
                      <GroupCardView key={g.group_key} card={g} onOpen={(id) => navigate(`/memory/chunk/${id}`)} />
                    ))}
                  </div>
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
            <div style={{ padding: '12px 8px' }}>
              <EntityGraph
                data={graph}
                height={430}
                onSelect={(label) => navigate(`/wiki?entity=${encodeURIComponent(label)}`)}
              />
              <p style={{ fontSize: 11.5, color: 'var(--tawn-text-3)', textAlign: 'center', marginTop: 6, fontFamily: 'var(--tawn-font-mono)' }}>
                {graph.nodes.length} entities · click one to open its wiki page
              </p>
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
            {enrich && (
              <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--tawn-line)' }}>
                <div style={{ fontSize: 12, color: 'var(--tawn-text-2)', marginBottom: 8 }}>
                  {enrich.chunks_enriched}/{enrich.chunks_total} summarised
                  {enrich.pending > 0 && ` · ${enrich.pending} pending`}
                </div>
                <Button variant="secondary" onClick={handleEnrich} disabled={enrichBusy}>
                  {enrichBusy ? 'enriching…' : 'enrich next 200'}
                </Button>
                {enrichMsg && <p style={{ fontSize: 12, color: 'var(--tawn-text-2)', marginTop: 8, fontFamily: 'var(--tawn-font-mono)' }}>{enrichMsg}</p>}
              </div>
            )}
            {compileStatus && <p style={{ fontSize: 12, color: 'var(--tawn-text-2)', marginTop: 8, fontFamily: 'var(--tawn-font-mono)' }}>{compileStatus}</p>}
          </Card>
        </div>
      </div>
    </>
  )
}
