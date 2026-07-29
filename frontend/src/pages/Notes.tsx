import { FormEvent, useEffect, useState } from 'react'
import { Card, Input, Textarea, Button, Badge } from '../ds'
import { useErrors } from '../components/Errors'
import {
  getNotes, putNote, deleteNote, postNote,
  type PersonalNote,
} from '../lib/api'

const DOMAINS = ['work', 'wealth', 'research', 'academic', 'hobby'] as const
type Domain = typeof DOMAINS[number]

function NoteRow({ note, onChanged }: { note: PersonalNote; onChanged: () => void }) {
  const [editing, setEditing] = useState(false)
  const [body, setBody] = useState(note.body)
  const [domain, setDomain] = useState(note.domain ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const dom = DOMAINS.includes(note.domain as Domain) ? (note.domain as Domain) : undefined

  async function save() {
    setBusy(true)
    setErr('')
    try {
      await putNote(note.id, { body, domain: domain || null })
      setEditing(false)
      onChanged()
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    // A note is something the user wrote deliberately and stored nowhere else.
    if (!window.confirm('Delete this note? It exists nowhere else and cannot be recovered.')) return
    setBusy(true)
    try {
      await deleteNote(note.id)
      onChanged()
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }

  return (
    <div style={{ padding: '14px 0', borderBottom: '1px solid var(--tawn-line)' }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
        {dom && <Badge domain={dom}>{dom}</Badge>}
        <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)' }}>
          {note.asof ? new Date(note.asof).toLocaleString() : 'undated'}
        </span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          {!editing && (
            <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>edit</Button>
          )}
          {editing && (
            <>
              <Button size="sm" onClick={save} disabled={busy}>{busy ? 'saving…' : 'save'}</Button>
              <Button variant="secondary" size="sm" onClick={() => { setBody(note.body); setEditing(false) }}>cancel</Button>
            </>
          )}
          <Button variant="secondary" size="sm" onClick={remove} disabled={busy}>delete</Button>
        </span>
      </div>

      {editing ? (
        <>
          <Textarea rows={4} value={body} onChange={(e) => setBody(e.target.value)} />
          <Input
            placeholder="domain (optional)"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            style={{ marginTop: 8, maxWidth: 220 }}
          />
        </>
      ) : (
        <div style={{ fontSize: 13.5, lineHeight: 1.65, color: 'var(--tawn-text)', whiteSpace: 'pre-wrap' }}>
          {note.body}
        </div>
      )}
      {err && <p style={{ fontSize: 12, color: 'var(--tawn-crit)', marginTop: 6 }}>{err}</p>}
    </div>
  )
}

export default function Notes() {
  const { report } = useErrors()
  const reportError = (e: unknown) => report(e instanceof Error ? e.message : String(e))
  const [notes, setNotes] = useState<PersonalNote[]>([])
  const [total, setTotal] = useState(0)
  const [domainFilter, setDomainFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [newBody, setNewBody] = useState('')
  const [newDomain, setNewDomain] = useState('')
  const [status, setStatus] = useState('')

  function load() {
    setLoading(true)
    getNotes({ domain: domainFilter || undefined, limit: 200 })
      .then((p) => { setNotes(p.notes); setTotal(p.total) })
      .catch(reportError)
      .finally(() => setLoading(false))
  }

  useEffect(load, [domainFilter])

  async function add(e: FormEvent) {
    e.preventDefault()
    if (!newBody.trim()) return
    setStatus('saving…')
    try {
      await postNote(newBody.trim(), newDomain.trim() || undefined)
      setNewBody('')
      setNewDomain('')
      setStatus('saved')
      load()
    } catch (err: unknown) {
      setStatus(`error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  return (
    <>
      <div style={{ maxWidth: 800, margin: '0 auto', padding: '32px 24px 64px' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>notes</h1>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginBottom: 20 }}>
          what you told your twin yourself — editable, and recompiled into memory when changed.
        </p>

        <Card style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
            add a note
          </div>
          <form onSubmit={add}>
            <Textarea rows={3} placeholder="What do you want to remember?" value={newBody} onChange={(e) => setNewBody(e.target.value)} />
            <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <Input placeholder="domain (optional)" value={newDomain} onChange={(e) => setNewDomain(e.target.value)} style={{ flex: 1, minWidth: 140 }} />
              <Button type="submit">save</Button>
            </div>
          </form>
          {status && <p style={{ fontSize: 12, color: 'var(--tawn-text-2)', marginTop: 8, fontFamily: 'var(--tawn-font-mono)' }}>{status}</p>}
        </Card>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
          <select
            value={domainFilter}
            onChange={(e) => setDomainFilter(e.target.value)}
            style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', padding: '5px 8px', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', background: 'var(--tawn-raised)', color: 'var(--tawn-text)' }}
          >
            <option value="">all domains</option>
            {DOMAINS.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
          <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)' }}>
            {total} note{total === 1 ? '' : 's'}
          </span>
        </div>

        <Card padded={false}>
          <div style={{ padding: '0 20px' }}>
            {loading ? (
              <div style={{ padding: '24px 0', fontSize: 13, color: 'var(--tawn-text-2)', textAlign: 'center' }}>loading…</div>
            ) : notes.length > 0 ? (
              notes.map((n) => <NoteRow key={n.id} note={n} onChanged={load} />)
            ) : (
              <div style={{ padding: '24px 0', fontSize: 13, color: 'var(--tawn-text-2)', textAlign: 'center' }}>
                nothing written yet — add your first note above.
              </div>
            )}
            <div style={{ height: 4 }} />
          </div>
        </Card>
      </div>
    </>
  )
}
