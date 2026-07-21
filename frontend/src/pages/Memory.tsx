import { useState } from 'react'
import { postNote, postRecall, postCompile, getCompileStatus, getBrief, BriefResult, RecallResult } from '../lib/api'

const S = {
  page: { maxWidth: 720, margin: '0 auto', padding: '32px 20px' } as const,
  h1: { fontSize: 22, fontWeight: 700, marginBottom: 24, letterSpacing: '-0.02em' } as const,
  section: { marginBottom: 36 } as const,
  label: { fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase' as const, letterSpacing: '0.08em', marginBottom: 8, display: 'block' },
  row: { display: 'flex', gap: 8, marginBottom: 8 } as const,
  input: {
    flex: 1, padding: '8px 12px', fontSize: 14,
    background: 'var(--tawn-surface)', border: '1px solid var(--tawn-line)',
    borderRadius: 6, color: 'var(--tawn-text)',
  } as const,
  textarea: {
    width: '100%', minHeight: 80, padding: '8px 12px', fontSize: 14, resize: 'vertical' as const,
    background: 'var(--tawn-surface)', border: '1px solid var(--tawn-line)',
    borderRadius: 6, color: 'var(--tawn-text)', boxSizing: 'border-box' as const,
  } as const,
  btn: {
    padding: '8px 16px', fontSize: 13, fontWeight: 600,
    background: 'var(--tawn-sandstone)', color: '#fff',
    border: 'none', borderRadius: 6, cursor: 'pointer', whiteSpace: 'nowrap' as const,
  } as const,
  btnSecondary: {
    padding: '8px 16px', fontSize: 13, fontWeight: 500,
    background: 'var(--tawn-surface)', color: 'var(--tawn-text-2)',
    border: '1px solid var(--tawn-line)', borderRadius: 6, cursor: 'pointer',
  } as const,
  card: {
    background: 'var(--tawn-surface)', border: '1px solid var(--tawn-line)',
    borderRadius: 8, padding: '12px 16px', marginBottom: 8,
  } as const,
  meta: { fontSize: 11, color: 'var(--tawn-text-2)', marginBottom: 4 } as const,
  content: { fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap' as const } as const,
  status: { fontSize: 13, color: 'var(--tawn-text-2)', marginTop: 8 } as const,
}

export default function Memory() {
  const [noteText, setNoteText] = useState('')
  const [noteDomain, setNoteDomain] = useState('')
  const [noteStatus, setNoteStatus] = useState('')

  const [query, setQuery] = useState('')
  const [recallResult, setRecallResult] = useState<RecallResult | null>(null)
  const [recallStatus, setRecallStatus] = useState('')

  const [compileStatus, setCompileStatus] = useState('')

  const [briefDomain, setBriefDomain] = useState('*')
  const [briefData, setBriefData] = useState<BriefResult | null>(null)
  const [briefStatus, setBriefStatus] = useState('')

  async function handleNote(e: React.FormEvent) {
    e.preventDefault()
    if (!noteText.trim()) return
    setNoteStatus('saving…')
    try {
      const res = await postNote(noteText.trim(), noteDomain.trim() || undefined)
      setNoteStatus(`saved → ${res.path}`)
      setNoteText('')
    } catch (err: unknown) {
      setNoteStatus(`error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  async function handleRecall(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    setRecallStatus('searching…')
    setRecallResult(null)
    try {
      const res = await postRecall(query.trim())
      setRecallResult(res)
      if (res.format === 'composed') {
        setRecallStatus('composed answer')
      } else {
        const count = res.chunks?.length ?? 0
        setRecallStatus(count ? `${count} result${count > 1 ? 's' : ''}` : 'no results')
      }
    } catch (err: unknown) {
      setRecallStatus(`error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  async function handleCompile() {
    setCompileStatus('compiling…')
    try {
      const res = await postCompile()
      setCompileStatus(
        res.ok
          ? `done — ${res.files_processed} files · +${res.chunks_added}/-${res.chunks_removed} chunks · ${res.entities_resolved} entities`
          : `failed: ${res.error}`
      )
    } catch (err: unknown) {
      setCompileStatus(`error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  async function handleCompileStatus() {
    try {
      const res = await getCompileStatus()
      setCompileStatus(
        `pending: ${res.pending} · last: ${res.last_compiled ? res.last_compiled.slice(0, 19).replace('T', ' ') : 'never'}`
      )
    } catch (err: unknown) {
      setCompileStatus(`error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  async function handleBrief(e: React.FormEvent) {
    e.preventDefault()
    setBriefStatus('loading…')
    setBriefData(null)
    try {
      const res = await getBrief(briefDomain.trim() || '*')
      setBriefData(res)
      setBriefStatus('')
    } catch (err: unknown) {
      setBriefStatus(`error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  const chunks = recallResult?.chunks ?? []

  return (
    <div style={S.page}>
      <h1 style={S.h1}>memory</h1>

      {/* note */}
      <section style={S.section}>
        <span style={S.label}>write a note</span>
        <form onSubmit={handleNote}>
          <textarea
            style={S.textarea}
            placeholder="What do you want to remember?"
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
          />
          <div style={{ ...S.row, marginTop: 8 }}>
            <input
              style={S.input}
              placeholder="domain (optional)"
              value={noteDomain}
              onChange={(e) => setNoteDomain(e.target.value)}
            />
            <button type="submit" style={S.btn}>save note</button>
          </div>
        </form>
        {noteStatus && <p style={S.status}>{noteStatus}</p>}
      </section>

      {/* recall */}
      <section style={S.section}>
        <span style={S.label}>search memory</span>
        <form onSubmit={handleRecall}>
          <div style={S.row}>
            <input
              style={S.input}
              placeholder="search query…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button type="submit" style={S.btn}>recall</button>
          </div>
        </form>
        {recallStatus && <p style={S.status}>{recallStatus}</p>}
        {recallResult?.embed_error && (
          <p style={{ ...S.status, color: 'var(--tawn-sandstone)' }}>
            embed unavailable — using full-text search
          </p>
        )}
        {recallResult?.format === 'composed' && recallResult.answer && (
          <div style={S.card}>
            <p style={S.content}>{recallResult.answer}</p>
          </div>
        )}
        {chunks.map((c, i) => (
          <div key={i} style={S.card}>
            <p style={S.meta}>
              {c.source}{c.domain ? ` · ${c.domain}` : ''}{c.stale ? ' · stale' : ''}
            </p>
            <p style={S.content}>{c.content.slice(0, 600)}{c.content.length > 600 ? '…' : ''}</p>
          </div>
        ))}
      </section>

      {/* brief */}
      <section style={S.section}>
        <span style={S.label}>domain brief</span>
        <form onSubmit={handleBrief}>
          <div style={S.row}>
            <input
              style={S.input}
              placeholder="domain (or * for all)"
              value={briefDomain}
              onChange={(e) => setBriefDomain(e.target.value)}
            />
            <button type="submit" style={S.btn}>brief</button>
          </div>
        </form>
        {briefStatus && <p style={S.status}>{briefStatus}</p>}
        {briefData && (
          <div style={S.card}>
            <p style={S.meta}>
              {briefData.domain} · {briefData.chunk_count} chunks · {briefData.entity_count} entities
              {briefData.stale_chunk_count > 0 ? ` · ${briefData.stale_chunk_count} stale` : ''}
              {briefData.staleness_hours !== null ? ` · ${briefData.staleness_hours}h old` : ''}
            </p>
            {briefData.summary && <p style={S.content}>{briefData.summary}</p>}
            {briefData.last_compiled && (
              <p style={S.meta}>compiled: {briefData.last_compiled.slice(0, 19).replace('T', ' ')}</p>
            )}
          </div>
        )}
      </section>

      {/* compile */}
      <section style={S.section}>
        <span style={S.label}>compile</span>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginBottom: 12 }}>
          Re-index raw/ files into searchable chunks and regenerate the wiki.
        </p>
        <div style={S.row}>
          <button style={S.btn} onClick={handleCompile}>run compile</button>
          <button style={S.btnSecondary} onClick={handleCompileStatus}>check status</button>
        </div>
        {compileStatus && <p style={S.status}>{compileStatus}</p>}
      </section>
    </div>
  )
}
