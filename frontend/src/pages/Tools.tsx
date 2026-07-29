import { useEffect, useState } from 'react'
import { Card, Button, Badge, Input, Textarea } from '../ds'
import { useErrors } from '../components/Errors'
import {
  getMcpServers, getDiscoveredServers, adoptServers, mcpServerAction, getServerTools,
  getSkills, saveSkillApi, deleteSkill, syncSkills, importSkills,
  getGeneratedTools, showGeneratedTool, generateTool, generatedToolAction,
  type McpServerRow, type DiscoveredServer, type SkillRow, type GeneratedTool,
} from '../lib/api'

type Tab = 'servers' | 'skills' | 'generated'

const TABS: { key: Tab; label: string; hint: string }[] = [
  { key: 'servers', label: 'servers', hint: 'MCP servers your twin can call' },
  { key: 'skills', label: 'skills', hint: 'instructions, portable to every agent' },
  { key: 'generated', label: 'generated', hint: 'tools your twin wrote' },
]

const mono = 'var(--tawn-font-mono)'

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 10.5, fontFamily: mono, letterSpacing: '0.09em', textTransform: 'uppercase', color: 'var(--tawn-text-3)', marginBottom: 8 }}>
      {children}
    </div>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ padding: '22px 0', fontSize: 13, color: 'var(--tawn-text-2)', textAlign: 'center' }}>
      {children}
    </div>
  )
}

function Row({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '9px 0', borderBottom: '1px solid var(--tawn-line)', flexWrap: 'wrap' }}>
      {children}
    </div>
  )
}

// ── servers ───────────────────────────────────────────────────────────────────

function ServersTab() {
  const { report } = useErrors()
  const reportError = (e: unknown) => report(e instanceof Error ? e.message : String(e))
  const [servers, setServers] = useState<McpServerRow[]>([])
  const [found, setFound] = useState<DiscoveredServer[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [toolList, setToolList] = useState<{ name: string; description: string }[]>([])

  function load() {
    getMcpServers().then((p) => setServers(p.servers)).catch(reportError)
    getDiscoveredServers().then((p) => setFound(p.servers.filter((s) => !s.known))).catch(reportError)
  }
  useEffect(load, [])

  async function act(name: string, action: 'enable' | 'disable' | 'test' | 'remove') {
    setBusy(name)
    setNote(null)
    try {
      const r = await mcpServerAction(name, action)
      if (action === 'test') {
        setNote(r.ok ? `${name}: ${r.tool_count} tools reachable` : `${name}: ${r.error}`)
      } else if (action === 'enable' && r.callable === false) {
        // Enabling alone does not make it callable — say which gate is closed.
        setNote(`${name} is enabled, but not in the mcp: grant yet, so it still cannot be called.`)
      }
      load()
    } finally {
      setBusy(null)
    }
  }

  async function expand(name: string) {
    if (expanded === name) { setExpanded(null); return }
    setExpanded(name)
    setToolList([])
    try {
      setToolList((await getServerTools(name)).tools)
    } catch { /* cached list may be empty */ }
  }

  return (
    <>
      {found.length > 0 && (
        <Card style={{ marginBottom: 16, borderColor: 'var(--tawn-lapis)' }}>
          <SectionLabel>found in your other tools</SectionLabel>
          <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', lineHeight: 1.55, marginBottom: 10 }}>
            {found.map((s) => s.name).join(', ')} — configured in{' '}
            {[...new Set(found.map((s) => s.source.split(':')[1]))].join(', ')}.
            Adding them registers each one <strong>disabled</strong>; nothing runs until you turn it on.
          </p>
          <Button size="sm" onClick={async () => { await adoptServers(); load() }}>
            add {found.length} server{found.length === 1 ? '' : 's'}
          </Button>
        </Card>
      )}

      {note && (
        <Card style={{ marginBottom: 16 }}>
          <span style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>{note}</span>
        </Card>
      )}

      <Card padded={false}>
        <div style={{ padding: '14px 20px 0' }}><SectionLabel>registered</SectionLabel></div>
        <div style={{ padding: '0 20px 6px' }}>
          {servers.length === 0 ? (
            <Empty>no servers yet — adopt the ones your other tools already use, or add one with <code style={{ fontFamily: mono }}>tawn mcp add</code>.</Empty>
          ) : servers.map((s) => (
            <div key={s.name}>
              <Row>
                <span onClick={() => expand(s.name)} style={{ fontSize: 13, fontWeight: 600, fontFamily: mono, cursor: 'pointer' }}>
                  {s.name}
                </span>
                <span style={{ fontSize: 11, fontFamily: mono, color: 'var(--tawn-text-3)' }}>{s.transport}</span>
                {s.callable
                  ? <Badge status="good">callable</Badge>
                  : s.enabled
                    ? <Badge status="warn">needs grant</Badge>
                    : <Badge status="info">off</Badge>}
                {s.tool_count > 0 && (
                  <span style={{ fontSize: 11.5, fontFamily: mono, color: 'var(--tawn-text-3)' }}>
                    {s.tool_count} tools
                  </span>
                )}
                <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
                  <Button variant="secondary" size="sm" disabled={busy === s.name} onClick={() => act(s.name, 'test')}>test</Button>
                  <Button variant="secondary" size="sm" disabled={busy === s.name} onClick={() => act(s.name, s.enabled ? 'disable' : 'enable')}>
                    {s.enabled ? 'disable' : 'enable'}
                  </Button>
                </span>
              </Row>
              {expanded === s.name && (
                <div style={{ padding: '4px 0 12px 12px' }}>
                  {toolList.length === 0
                    ? <span style={{ fontSize: 12, color: 'var(--tawn-text-3)' }}>no tools cached — run test to fetch them.</span>
                    : toolList.map((t) => (
                      <div key={t.name} style={{ fontSize: 12, padding: '3px 0' }}>
                        <span style={{ fontFamily: mono, color: 'var(--tawn-text)' }}>{t.name}</span>
                        <span style={{ color: 'var(--tawn-text-3)', marginLeft: 8 }}>{t.description.slice(0, 90)}</span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginTop: 12, lineHeight: 1.6 }}>
        A server is callable only when it is <strong>enabled</strong> here <em>and</em> its name is in{' '}
        <code style={{ fontFamily: mono }}>mcp:</code> in <code style={{ fontFamily: mono }}>~/.tawn/grants.yaml</code>.
        Two switches on purpose: the grant is your security decision, the toggle is your convenience one.
      </p>
    </>
  )
}

// ── skills ────────────────────────────────────────────────────────────────────

function SkillsTab() {
  const { report } = useErrors()
  const reportError = (e: unknown) => report(e instanceof Error ? e.message : String(e))
  const [skills, setSkills] = useState<SkillRow[]>([])
  const [targets, setTargets] = useState<string[]>([])
  const [editing, setEditing] = useState<SkillRow | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [pending, setPending] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  function load() {
    getSkills().then((p) => { setSkills(p.skills); setTargets(p.targets) }).catch(reportError)
    importSkills(true).then((p) => setPending(p.imported)).catch(reportError)
  }
  useEffect(load, [])

  async function doSync() {
    setBusy(true)
    try {
      const r = await syncSkills()
      const bits = [`${r.written.length} written to ${r.targets.join(', ') || 'nowhere'}`]
      if (r.conflicts.length) bits.push(`${r.conflicts.length} conflict(s): ${r.conflicts.join(', ')} — those files were not written by tawn, so they were left alone`)
      setNote(bits.join('. '))
      load()
    } finally { setBusy(false) }
  }

  async function doImport() {
    setBusy(true)
    try {
      const r = await importSkills(false)
      setNote(`imported ${r.imported.length}${r.conflicts.length ? `, ${r.conflicts.length} name conflict(s) skipped` : ''}`)
      load()
    } finally { setBusy(false) }
  }

  async function save() {
    if (!editing?.name.trim()) return
    await saveSkillApi({ name: editing.name, description: editing.description, body: editing.body })
    setEditing(null)
    load()
  }

  return (
    <>
      {pending.length > 0 && (
        <Card style={{ marginBottom: 16, borderColor: 'var(--tawn-lapis)' }}>
          <SectionLabel>found in your other agents</SectionLabel>
          <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', lineHeight: 1.55, marginBottom: 10 }}>
            {pending.join(', ')} — {pending.length} skill{pending.length === 1 ? '' : 's'} you already
            have elsewhere. Importing copies them here; a name you already use is skipped, never overwritten.
          </p>
          <Button size="sm" disabled={busy} onClick={doImport}>import {pending.length}</Button>
        </Card>
      )}

      {note && (
        <Card style={{ marginBottom: 16 }}>
          <span style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>{note}</span>
        </Card>
      )}

      {editing && (
        <Card style={{ marginBottom: 16 }}>
          <SectionLabel>{skills.find((s) => s.name === editing.name) ? 'edit skill' : 'new skill'}</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
            <Input placeholder="name, e.g. review-migrations" value={editing.name}
                   onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
            <Input placeholder="one line — when should the agent use this?" value={editing.description}
                   onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
            <Textarea rows={10} placeholder="Markdown instructions addressed to the agent…" value={editing.body}
                      onChange={(e) => setEditing({ ...editing, body: e.target.value })} />
            <div style={{ display: 'flex', gap: 8 }}>
              <Button size="sm" onClick={save} disabled={!editing.name.trim()}>save</Button>
              <Button size="sm" variant="secondary" onClick={() => setEditing(null)}>cancel</Button>
            </div>
          </div>
        </Card>
      )}

      <Card padded={false}>
        <div style={{ display: 'flex', alignItems: 'center', padding: '14px 20px 0' }}>
          <SectionLabel>your skills</SectionLabel>
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 6, paddingBottom: 8 }}>
            <Button size="sm" variant="secondary" onClick={() => setEditing({ name: '', description: '', body: '', source: 'authored', imported_from: null })}>
              new
            </Button>
            <Button size="sm" variant="secondary" disabled={busy || skills.length === 0} onClick={doSync}>
              {busy ? 'syncing…' : `sync${targets.length ? ` → ${targets.length}` : ''}`}
            </Button>
          </span>
        </div>
        <div style={{ padding: '0 20px 6px' }}>
          {skills.length === 0 ? (
            <Empty>no skills yet — write one, or import the ones your other agents already have.</Empty>
          ) : skills.map((s) => (
            <Row key={s.name}>
              <span style={{ fontSize: 13, fontWeight: 600, fontFamily: mono }}>{s.name}</span>
              {s.imported_from && <Badge status="info">from {s.imported_from}</Badge>}
              <span style={{ fontSize: 12.5, color: 'var(--tawn-text-2)', flex: 1, minWidth: 120 }}>
                {s.description}
              </span>
              <span style={{ display: 'flex', gap: 6 }}>
                <Button size="sm" variant="secondary" onClick={() => setEditing(s)}>edit</Button>
                <Button size="sm" variant="secondary" onClick={async () => {
                  // A skill is authored content; it exists nowhere else.
                  if (!window.confirm(`Delete the skill "${s.name}"? This cannot be undone.`)) return
                  await deleteSkill(s.name); load()
                }}>delete</Button>
              </span>
            </Row>
          ))}
        </div>
      </Card>

      <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginTop: 12, lineHeight: 1.6 }}>
        Sync writes each skill into every agent detected on this machine. It never deletes or overwrites
        a file it did not write, so a skill you wrote by hand under the same name is reported as a
        conflict and left exactly as it is.
      </p>
    </>
  )
}

// ── generated ─────────────────────────────────────────────────────────────────

function GeneratedTab() {
  const { report } = useErrors()
  const reportError = (e: unknown) => report(e instanceof Error ? e.message : String(e))
  const [tools, setTools] = useState<GeneratedTool[]>([])
  const [desc, setDesc] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [source, setSource] = useState<{ name: string; text: string } | null>(null)
  // Enabling is deliberately gated on having opened the source: a generated
  // tool is called by a model on its own initiative, so the review is the
  // protection, not a formality.
  const [reviewed, setReviewed] = useState<Set<string>>(new Set())

  function load() {
    getGeneratedTools().then((p) => setTools(p.tools)).catch(reportError)
  }
  useEffect(load, [])

  async function create() {
    if (!desc.trim()) return
    setBusy(true)
    setNote(null)
    try {
      const r = await generateTool(desc.trim())
      setNote(r.ok
        ? `wrote ${r.name} — disabled. Read the source, then enable it.`
        : r.kind === 'capability_mismatch'
          ? `rejected: ${r.error}. The code needs more access than it declared, so nothing was written.`
          : `could not generate: ${r.error}`)
      if (r.ok) setDesc('')
      load()
    } finally { setBusy(false) }
  }

  async function view(name: string) {
    if (source?.name === name) { setSource(null); return }
    const r = await showGeneratedTool(name)
    setSource({ name, text: r.source ?? '(no source)' })
    setReviewed((prev) => new Set(prev).add(name))
  }

  async function act(name: string, action: 'enable' | 'disable' | 'test' | 'remove') {
    const r = await generatedToolAction(name, action)
    if (action === 'test') setNote(r.output ?? '')
    load()
  }

  return (
    <>
      <Card style={{ marginBottom: 16 }}>
        <SectionLabel>describe a tool</SectionLabel>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Input
            style={{ flex: 1, minWidth: 220 }}
            placeholder="e.g. fetch the current NGX price for a ticker"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') create() }}
          />
          <Button onClick={create} disabled={busy || !desc.trim()}>{busy ? 'writing…' : 'generate'}</Button>
        </div>
        <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginTop: 9, lineHeight: 1.6 }}>
          Generated tools arrive disabled. What the code declares it needs is checked against what it
          actually does, and a mismatch is rejected outright.
        </p>
      </Card>

      {note && (
        <Card style={{ marginBottom: 16 }}>
          <pre style={{ fontSize: 12, fontFamily: mono, color: 'var(--tawn-text-2)', whiteSpace: 'pre-wrap', margin: 0, maxHeight: 220, overflowY: 'auto' }}>
            {note}
          </pre>
        </Card>
      )}

      <Card padded={false}>
        <div style={{ padding: '14px 20px 0' }}><SectionLabel>your tools</SectionLabel></div>
        <div style={{ padding: '0 20px 6px' }}>
          {tools.length === 0 ? (
            <Empty>none yet — describe one above.</Empty>
          ) : tools.map((t) => (
            <div key={t.name}>
              <Row>
                <span style={{ fontSize: 13, fontWeight: 600, fontFamily: mono }}>{t.name}</span>
                {t.enabled
                  ? (t.granted ? <Badge status="good">live</Badge> : <Badge status="warn">needs grant</Badge>)
                  : <Badge status="info">off</Badge>}
                {t.capabilities.map((c) => (
                  <span key={c} style={{ fontSize: 10.5, fontFamily: mono, padding: '1px 7px', borderRadius: 999, border: '1px solid var(--tawn-line)', color: 'var(--tawn-text-3)' }}>
                    {c}
                  </span>
                ))}
                <span style={{ fontSize: 12.5, color: 'var(--tawn-text-2)', flex: 1, minWidth: 120 }}>
                  {t.description}
                </span>
                <span style={{ display: 'flex', gap: 6 }}>
                  <Button size="sm" variant="secondary" onClick={() => view(t.name)}>
                    {source?.name === t.name ? 'hide' : 'source'}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => act(t.name, 'test')}>test</Button>
                  <span title={!t.enabled && !reviewed.has(t.name) ? 'read the source first' : undefined}>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={!t.enabled && !reviewed.has(t.name)}
                      onClick={() => act(t.name, t.enabled ? 'disable' : 'enable')}
                    >
                      {t.enabled ? 'disable' : 'enable'}
                    </Button>
                  </span>
                  <Button size="sm" variant="secondary" onClick={() => {
                    if (!window.confirm(`Delete the tool "${t.name}" and its source? This cannot be undone.`)) return
                    act(t.name, 'remove')
                  }}>delete</Button>
                </span>
              </Row>
              {source?.name === t.name && (
                <pre style={{ fontSize: 12, fontFamily: mono, background: 'var(--tawn-raised)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', padding: 12, margin: '6px 0 12px', overflowX: 'auto', lineHeight: 1.6 }}>
                  {source.text}
                </pre>
              )}
            </div>
          ))}
        </div>
      </Card>

      <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginTop: 12, lineHeight: 1.6 }}>
        An enabled tool runs in Tawn's own process with Tawn's access. The capability check stops a tool
        acquiring access you never granted, and stops it running before a human has looked at it — but it
        is not a sandbox. Read the source before enabling anything.
      </p>
    </>
  )
}

// ── page ──────────────────────────────────────────────────────────────────────

export default function Tools() {
  const [tab, setTab] = useState<Tab>('servers')
  const active = TABS.find((t) => t.key === tab)!

  return (
    <>
      <div style={{ maxWidth: 940, margin: '0 auto', padding: '32px 24px 64px' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>tools</h1>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginBottom: 18 }}>
          what your twin can do — and what it needs your permission for.
        </p>

        <div style={{ display: 'flex', gap: 4, marginBottom: 6, flexWrap: 'wrap' }}>
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                fontSize: 13, padding: '6px 13px', cursor: 'pointer',
                border: '1px solid var(--tawn-line)', borderRadius: 999,
                background: tab === t.key ? 'var(--tawn-lapis-soft)' : 'transparent',
                color: tab === t.key ? 'var(--tawn-lapis)' : 'var(--tawn-text-2)',
                fontWeight: tab === t.key ? 600 : 400,
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
        <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginBottom: 18 }}>{active.hint}</p>

        {tab === 'servers' && <ServersTab />}
        {tab === 'skills' && <SkillsTab />}
        {tab === 'generated' && <GeneratedTab />}
      </div>
    </>
  )
}
