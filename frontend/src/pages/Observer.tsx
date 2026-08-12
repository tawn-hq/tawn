import { useCallback, useEffect, useState } from 'react'
import { Card, Button, Badge, Select, Checkbox, StatCard, Input } from '../ds'
import { useErrors } from '../components/Errors'
import {
  getObserverProjects, getObserverSessions, getObserverEvents,
  getReviewModels, postObserverReview, postObserverSweep, getObserverNote,
  type ObserverProject, type ObserverSession, type ObserverEvent,
  type CloudModelRow,
} from '../lib/api'

const mono = 'var(--tawn-font-mono)'

/** Substring match, so "claude" narrows 488 models to the handful worth reading. */
function matches(target: string, filter: string): boolean {
  return !filter || target.toLowerCase().includes(filter.toLowerCase())
}

/** Low confidence must read as a guess wherever it appears, not only in totals. */
function ActorTag({ actor, confidence }: { actor: string; confidence: string }) {
  const weak = confidence !== 'high'
  return (
    <span
      style={{
        fontFamily: mono, fontSize: 11,
        color: weak ? 'var(--tawn-text-3)' : 'var(--tawn-text-2)',
      }}
      title={weak ? 'heuristic — treat as a guess' : 'corroborated by git or a session log'}
    >
      {weak ? 'likely ' : ''}{actor}
    </span>
  )
}

function noteBadge(state: string | null) {
  if (state === 'written') return <Badge>note written</Badge>
  if (state === 'unanalysed') return <Badge>facts only</Badge>
  if (state === 'failed') return <Badge>note failed</Badge>
  return <Badge>awaiting note</Badge>
}

function NoteView({ id }: { id: number }) {
  const [note, setNote] = useState<{ found: boolean; body?: string; reason?: string; path?: string } | null>(null)
  const { report } = useErrors()

  useEffect(() => {
    getObserverNote(id).then(setNote).catch(e => report(String(e)))
  }, [id, report])

  if (!note) return <p style={{ fontSize: 12, color: 'var(--tawn-text-3)' }}>loading…</p>
  if (!note.found) {
    return (
      <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginTop: 8 }}>
        {note.reason}
        {note.path && <><br /><span style={{ fontFamily: mono, fontSize: 10 }}>{note.path}</span></>}
      </p>
    )
  }
  return (
    <pre
      style={{
        marginTop: 10, padding: 12, fontSize: 12, lineHeight: 1.6,
        fontFamily: mono, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        background: 'var(--tawn-raised)', border: '1px solid var(--tawn-line)',
        borderRadius: 'var(--tawn-radius-sm)', overflowX: 'auto',
      }}
    >{note.body}</pre>
  )
}

function EventList({ id }: { id: number }) {
  const [events, setEvents] = useState<ObserverEvent[] | null>(null)
  const { report } = useErrors()

  useEffect(() => {
    getObserverEvents(id).then(r => setEvents(r.events)).catch(e => report(String(e)))
  }, [id, report])

  if (!events) return <p style={{ fontSize: 12, color: 'var(--tawn-text-3)' }}>loading…</p>
  if (!events.length) return <p style={{ fontSize: 12, color: 'var(--tawn-text-3)' }}>no events</p>

  return (
    <div style={{ marginTop: 10, borderTop: '1px solid var(--tawn-line)', paddingTop: 10 }}>
      {events.map((e, i) => (
        <div
          key={i}
          style={{
            display: 'flex', gap: 10, alignItems: 'baseline',
            padding: '3px 0', fontSize: 12, flexWrap: 'wrap',
          }}
        >
          <span style={{ fontFamily: mono, color: 'var(--tawn-text-3)', minWidth: 62 }}>{e.kind}</span>
          <span style={{ fontFamily: mono, flex: 1, minWidth: 200, wordBreak: 'break-all' }}>{e.path}</span>
          <span style={{ fontFamily: mono, color: 'var(--tawn-text-3)' }}>
            +{e.lines_added} −{e.lines_removed}
          </span>
          <ActorTag actor={e.actor} confidence={e.confidence} />
          <span style={{ fontFamily: mono, fontSize: 10, color: 'var(--tawn-text-3)' }}>via {e.basis}</span>
        </div>
      ))}
    </div>
  )
}

export default function Observer() {
  const [projects, setProjects] = useState<ObserverProject[]>([])
  const [tiers, setTiers] = useState<string[]>([])
  const [sessions, setSessions] = useState<ObserverSession[]>([])
  const [open, setOpen] = useState<number | null>(null)
  const [openNote, setOpenNote] = useState<number | null>(null)
  const [project, setProject] = useState('')
  const [cloud, setCloud] = useState(false)
  const [model, setModel] = useState('')
  const [models, setModels] = useState<{
    local: string[]
    cloud: string[]
    cloud_detail: CloudModelRow[]
    providers: string[]
    default: string | null
    cloud_available: boolean
  } | null>(null)
  const [modelFilter, setModelFilter] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState('')
  const [sweepMsg, setSweepMsg] = useState('')
  const { report } = useErrors()

  const load = useCallback(() => {
    getObserverProjects().then(r => { setProjects(r.projects); setTiers(r.observe) }).catch(e => report(String(e)))
    getObserverSessions(40).then(r => setSessions(r.sessions)).catch(e => report(String(e)))
  }, [report])

  useEffect(() => {
    load()
    getReviewModels().then(setModels).catch(() => setModels(null))
  }, [load])

  async function review() {
    setBusy(true)
    setResult('')
    try {
      const r = await postObserverReview(project || undefined, {
        cloud: cloud && !model,
        model: model || undefined,
      })
      setResult(`closed ${r.closed} session(s), wrote ${r.notes_written} note(s) using ${r.model}`)
      load()
    } catch (e: unknown) {
      report(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function runSweep(dryRun: boolean) {
    setBusy(true)
    setSweepMsg('')
    try {
      const r = await postObserverSweep(project || undefined, dryRun)
      const lines = r.results.map(x => {
        const bits = []
        if (x.commits_read) bits.push(`${x.commits_read} commit(s)`)
        if (x.events_added) bits.push(`+${x.events_added}`)
        if (x.events_updated) bits.push(`${x.events_updated} corrected`)
        if (x.skipped_existing) bits.push(`${x.skipped_existing} already recorded`)
        const body = bits.join(', ') || 'nothing to reconcile'
        return `${x.project}: ${body}${x.reason ? ` — ${x.reason}` : ''}`
      })
      setSweepMsg((dryRun ? 'would record — ' : '') + lines.join(' · '))
      if (!dryRun) load()
    } catch (e: unknown) {
      report(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const off = tiers.length === 0
  const pending = sessions.filter(s => !s.note_state || s.note_state === 'pending_note').length

  return (
    <>
      {off && (
        <Card>
          <h3 style={{ margin: 0, fontSize: 14 }}>The observer is not watching anything</h3>
          <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', margin: '8px 0 0' }}>
            No tier is enabled, so nothing is being attributed. Add{' '}
            <code style={{ fontFamily: mono }}>observe: [fs, git, agents]</code> under Settings → Grants,
            confirm the change, then start the watcher with{' '}
            <code style={{ fontFamily: mono }}>tawn web</code> or{' '}
            <code style={{ fontFamily: mono }}>tawn observe start</code>.
          </p>
        </Card>
      )}

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', margin: '12px 0' }}>
        <StatCard label="tiers" value={tiers.length ? tiers.join(', ') : 'none'} />
        <StatCard label="projects watched" value={String(projects.length)} />
        <StatCard label="sessions" value={String(sessions.length)} />
        <StatCard label="awaiting a note" value={String(pending)} />
      </div>

      <Card>
        <h3 style={{ margin: 0, fontSize: 14 }}>Write review notes</h3>
        <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', margin: '6px 0 12px' }}>
          Closes the open session and writes its note. The file list is always rendered from the
          record; only the written analysis comes from a model, and an unusable answer is dropped
          rather than saved.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label style={{ fontSize: 12 }}>
            project
            <Select value={project} onChange={e => setProject(e.target.value)}>
              <option value="">all watched projects</option>
              {projects.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
            </Select>
          </label>

          <label style={{ fontSize: 12 }}>
            model
            <Select value={model} onChange={e => setModel(e.target.value)}>
              <option value="">
                automatic{models?.default ? ` — ${models.default}` : ''}
              </option>
              {models?.local.length ? (
                <optgroup label="local">
                  {models.local
                    .filter(m => matches(m, modelFilter))
                    .map(m => <option key={m} value={m}>{m}</option>)}
                </optgroup>
              ) : null}
              {/* Grouped per provider: OpenRouter alone fronts hundreds of
                  models, and one flat list of them is not a chooser. */}
              {(models?.providers ?? []).map(prov => {
                const rows = (models?.cloud_detail ?? [])
                  .filter(r => r.provider === prov && matches(r.target, modelFilter))
                if (!rows.length) return null
                return (
                  <optgroup key={prov} label={`${prov} — sends file paths off this machine`}>
                    {rows.map(r => (
                      <option key={r.target} value={r.target}>
                        {r.model}{r.source !== 'live' ? ` (${r.source})` : ''}
                      </option>
                    ))}
                  </optgroup>
                )
              })}
            </Select>
          </label>

          {(models?.cloud.length ?? 0) > 20 && (
            <label style={{ fontSize: 12 }}>
              filter
              <Input
                value={modelFilter}
                onChange={e => setModelFilter(e.target.value)}
                placeholder="claude, gpt, llama…"
                mono
                style={{ width: 150 }}
              />
            </label>
          )}

          <Checkbox
            checked={cloud}
            disabled={!!model || !models?.cloud_available}
            onChange={e => setCloud(e.target.checked)}
            label="allow a cloud model"
          />

          <Button onClick={review} disabled={busy || off}>
            {busy ? 'writing…' : 'write notes'}
          </Button>
        </div>

        {cloud && !model && (
          <p style={{ fontSize: 12, color: 'var(--tawn-warn, #b45309)', marginTop: 10 }}>
            File paths and line counts for this session will be sent to a cloud provider. File
            contents are never sent.
          </p>
        )}
        {!models?.cloud_available && (
          <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginTop: 10 }}>
            No cloud provider key is set, so local models are the only option. Add one under
            Settings → Models.
          </p>
        )}
        {result && (
          <p style={{ fontSize: 12, fontFamily: mono, marginTop: 10 }}>{result}</p>
        )}
      </Card>

      <Card>
        <h3 style={{ margin: 0, fontSize: 14 }}>Reconcile against git and disk</h3>
        <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', margin: '6px 0 12px' }}>
          The watcher only sees what happened while it was running — not the ~15s it
          takes to arm, and nothing at all while it was stopped. This fills those gaps
          from git history and a filesystem snapshot, so a note says what changed
          rather than what was observed. A first run takes a baseline and reports
          nothing; changes appear from the next one.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <Button variant="secondary" onClick={() => runSweep(true)} disabled={busy}>
            preview
          </Button>
          <Button onClick={() => runSweep(false)} disabled={busy}>
            {busy ? 'reconciling…' : 'reconcile'}
          </Button>
        </div>
        {sweepMsg && (
          <p style={{ fontSize: 12, fontFamily: mono, marginTop: 10, lineHeight: 1.6 }}>
            {sweepMsg}
          </p>
        )}
      </Card>

      <Card>
        <h3 style={{ margin: 0, fontSize: 14 }}>Sessions</h3>
        {!sessions.length && (
          <p style={{ fontSize: 13, color: 'var(--tawn-text-3)', marginTop: 8 }}>
            Nothing recorded yet. The watcher needs about half a minute to arm across large
            projects before it sees anything.
          </p>
        )}
        {sessions.map(s => (
          <div key={s.id} style={{ padding: '12px 0', borderBottom: '1px solid var(--tawn-line)' }}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <strong style={{ fontSize: 13 }}>{s.project}</strong>
              <span style={{ fontFamily: mono, fontSize: 11, color: 'var(--tawn-text-3)' }}>
                {s.started_at ? new Date(s.started_at).toLocaleString() : '—'}
                {s.ended_at ? '' : ' · open'}
              </span>
              <span style={{ fontFamily: mono, fontSize: 11 }}>
                {s.event_count} files · +{s.lines_added} −{s.lines_removed}
              </span>
              {noteBadge(s.note_state)}
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
                {s.note_path && (
                  <Button
                    variant="ghost"
                    onClick={() => setOpenNote(openNote === s.id ? null : s.id)}
                  >
                    {openNote === s.id ? 'hide note' : 'read note'}
                  </Button>
                )}
                <Button variant="ghost" onClick={() => setOpen(open === s.id ? null : s.id)}>
                  {open === s.id ? 'hide files' : 'show files'}
                </Button>
              </span>
            </div>
            <p style={{ fontFamily: mono, fontSize: 11, color: 'var(--tawn-text-2)', margin: '6px 0 0' }}>
              {s.attribution}
            </p>
            {s.note_path && (
              <p style={{ fontFamily: mono, fontSize: 10, color: 'var(--tawn-text-3)', margin: '4px 0 0', wordBreak: 'break-all' }}>
                {s.note_path}
              </p>
            )}
            {openNote === s.id && <NoteView id={s.id} />}
            {open === s.id && <EventList id={s.id} />}
          </div>
        ))}
      </Card>
    </>
  )
}
