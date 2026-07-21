import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Layout from '../components/Layout'
import { postDomainDraft, postDomainPromote, deleteDomainDraft, type DraftResponse } from '../lib/api'

type Stage = 'describe' | 'preview' | 'done'

export default function DomainCreate() {
  const navigate = useNavigate()
  const [stage, setStage] = useState<Stage>('describe')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [draft, setDraft] = useState<DraftResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [editedSource, setEditedSource] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function generate(e: FormEvent) {
    e.preventDefault()
    if (!name.trim() || !description.trim()) return
    setBusy(true)
    setError(null)
    try {
      const res = await postDomainDraft(name.trim(), description.trim())
      if (res.needs_wizard) {
        setError('No model configured — use the CLI: tawn domain create ' + name.trim())
        return
      }
      if (res.error) setError(res.error)
      setDraft(res)
      setEditedSource(res.source ?? '')
      setStage('preview')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'generation failed')
    } finally {
      setBusy(false)
    }
  }

  async function promote() {
    setBusy(true)
    setError(null)
    try {
      await postDomainPromote(name.trim())
      setStage('done')
      setTimeout(() => navigate('/'), 1500)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'promote failed')
    } finally {
      setBusy(false)
    }
  }

  async function discard() {
    try { await deleteDomainDraft(name.trim()) } catch { /* best-effort */ }
    setStage('describe')
    setDraft(null)
    setEditedSource('')
    setError(null)
  }

  const inputBase = {
    border: '1px solid var(--tawn-line)',
    borderRadius: 'var(--r-sm)',
    padding: '7px 12px',
    background: 'var(--tawn-raised)',
    color: 'var(--tawn-text)',
    fontSize: 'var(--sz-sm)',
    fontFamily: 'var(--tawn-font-body)',
    width: '100%',
    display: 'block' as const,
  }

  const btnPrimary = {
    padding: '8px 20px',
    background: 'var(--tawn-lapis)',
    color: '#fff',
    border: 'none',
    borderRadius: 'var(--r)',
    fontWeight: 600,
    cursor: busy ? 'wait' as const : 'pointer' as const,
    opacity: busy ? 0.5 : 1,
    fontSize: 'var(--sz-sm)',
  }

  const btnSecondary = {
    padding: '7px 14px',
    background: 'var(--tawn-raised)',
    border: '1px solid var(--tawn-line)',
    borderRadius: 'var(--r-sm)',
    cursor: 'pointer' as const,
    fontSize: 'var(--sz-sm)',
    color: 'var(--tawn-text)',
  }

  return (
    <Layout>
      <h1 style={{ fontSize: 'var(--sz-xl)', fontWeight: 700, marginBottom: 8 }}>create domain</h1>
      <p style={{ color: 'var(--tawn-text-2)', marginBottom: 28, fontSize: 'var(--sz-sm)' }}>
        Describe what you want to track. Tawn generates the module; you review before it goes live.
      </p>

      {stage === 'describe' && (
        <form onSubmit={generate} style={{ maxWidth: 520 }}>
          <label style={{ display: 'block', marginBottom: 14 }}>
            <span style={{ fontSize: 'var(--sz-sm)', fontWeight: 600, color: 'var(--tawn-text-2)' }}>
              Domain name (slug)
            </span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))}
              placeholder="my_domain"
              required
              style={{ ...inputBase, marginTop: 6, fontFamily: 'var(--tawn-font-mono)' }}
            />
          </label>
          <label style={{ display: 'block', marginBottom: 20 }}>
            <span style={{ fontSize: 'var(--sz-sm)', fontWeight: 600, color: 'var(--tawn-text-2)' }}>
              What do you want to track?
            </span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. track my gym workouts — sets, reps, and PRs per exercise"
              rows={4}
              required
              style={{ ...inputBase, marginTop: 6, resize: 'vertical' }}
            />
          </label>
          {error && <p style={{ color: 'var(--tawn-crit)', fontSize: 'var(--sz-sm)', marginBottom: 10 }}>{error}</p>}
          <button
            type="submit"
            disabled={busy || !name.trim() || !description.trim()}
            style={{ ...btnPrimary, opacity: busy || !name.trim() || !description.trim() ? 0.5 : 1 }}
          >
            {busy ? 'generating…' : 'generate with AI'}
          </button>
        </form>
      )}

      {stage === 'preview' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, alignItems: 'start' }}>
          <div>
            <h2 style={{ fontSize: 'var(--sz-sm)', fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
              generated source — {name}
            </h2>
            <textarea
              value={editedSource}
              onChange={(e) => setEditedSource(e.target.value)}
              rows={30}
              spellCheck={false}
              style={{ ...inputBase, fontFamily: 'var(--tawn-font-mono)', fontSize: 12, lineHeight: 1.6, resize: 'vertical' }}
            />
          </div>
          <div style={{ position: 'sticky', top: 64 }}>
            <h2 style={{ fontSize: 'var(--sz-sm)', fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
              info
            </h2>
            <div style={{ border: '1px solid var(--tawn-line)', borderRadius: 'var(--r)', padding: '14px 16px', marginBottom: 14, fontSize: 'var(--sz-sm)', color: 'var(--tawn-text-2)', lineHeight: 1.6 }}>
              <p style={{ marginBottom: 8 }}>Review the generated code. Edit directly in the left pane.</p>
              <p>Once promoted, the domain appears in the nav immediately.</p>
              {draft?.error && <p style={{ color: 'var(--tawn-warn)', marginTop: 8 }}>Preview: {draft.error}</p>}
            </div>
            {error && <p style={{ color: 'var(--tawn-crit)', fontSize: 'var(--sz-sm)', marginBottom: 10 }}>{error}</p>}
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={discard} style={btnSecondary}>← back</button>
              <button onClick={promote} disabled={busy} style={{ ...btnPrimary, flex: 1 }}>
                {busy ? 'promoting…' : 'promote & enable'}
              </button>
            </div>
          </div>
        </div>
      )}

      {stage === 'done' && (
        <div style={{ border: '1px solid var(--tawn-good)', borderRadius: 'var(--r)', padding: '16px 20px', color: 'var(--tawn-good)' }}>
          ✓ Domain <strong>{name}</strong> enabled. Redirecting…
        </div>
      )}
    </Layout>
  )
}
