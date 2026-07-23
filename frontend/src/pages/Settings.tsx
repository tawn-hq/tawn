import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppNav from '../components/AppNav'
import { Card, Input, Textarea, Button, Checkbox, Badge } from '../ds'

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
import { getGrants, putGrants, confirmGrants, getProfile, putProfile, getDomains, getAllModels, enableDomain, disableDomain, getKeyStatus, postKey, getChunkStats, deleteChunks, postCompile, getAudit, verifyAudit, type Grants, type DomainRow, type ModelRow, type ChunkStats, type AuditPage } from '../lib/api'
import { SetupWizard } from './Setup'
import { LogsPanel } from './Logs'

type Tab = 'grants' | 'personality' | 'domains' | 'models' | 'exports' | 'integrations' | 'setup' | 'audit' | 'logs' | 'updates' | 'database'

const TABS: { key: Tab; label: string; group: string }[] = [
  { key: 'grants', label: 'grants', group: 'privacy' },
  { key: 'personality', label: 'personality', group: 'privacy' },
  { key: 'domains', label: 'domains', group: 'system' },
  { key: 'models', label: 'models', group: 'system' },
  { key: 'exports', label: 'exports', group: 'data' },
  { key: 'integrations', label: 'integrations', group: 'data' },
  { key: 'setup', label: 'setup', group: 'admin' },
  { key: 'database', label: 'database', group: 'admin' },
  { key: 'audit', label: 'audit log', group: 'admin' },
  { key: 'logs', label: 'server logs', group: 'admin' },
  { key: 'updates', label: 'updates', group: 'admin' },
]

const GROUPS = ['privacy', 'system', 'data', 'admin']

function SideNav({ active, setActive, mobile }: { active: Tab; setActive: (t: Tab) => void; mobile: boolean }) {
  if (mobile) {
    // Fixed 160px column pushes content into a ~150px sliver on phones —
    // a horizontal scroll strip of flat pills (no group headers, they only
    // add vertical clutter in one row) keeps every tab reachable and full
    // width goes to the actual panel content below it.
    return (
      <nav style={{ display: 'flex', gap: 6, overflowX: 'auto', paddingBottom: 10, marginBottom: 4, WebkitOverflowScrolling: 'touch' }}>
        {TABS.map((t) => (
          <div
            key={t.key}
            onClick={() => setActive(t.key)}
            style={{
              cursor: 'pointer',
              padding: '7px 12px',
              borderRadius: 999,
              fontSize: 13,
              whiteSpace: 'nowrap',
              flexShrink: 0,
              fontWeight: active === t.key ? 600 : 400,
              color: active === t.key ? 'var(--tawn-lapis)' : 'var(--tawn-text-2)',
              background: active === t.key ? 'var(--tawn-lapis-soft)' : 'var(--tawn-raised)',
              border: '1px solid var(--tawn-line)',
              transition: 'background 0.12s',
              userSelect: 'none',
            }}
          >
            {t.label}
          </div>
        ))}
      </nav>
    )
  }
  return (
    <nav style={{ width: 160, flexShrink: 0, paddingTop: 2 }}>
      {GROUPS.map((g) => {
        const items = TABS.filter((t) => t.group === g)
        return (
          <div key={g} style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--tawn-text-3)', marginBottom: 6, paddingLeft: 10 }}>{g}</div>
            {items.map((t) => (
              <div
                key={t.key}
                onClick={() => setActive(t.key)}
                style={{
                  cursor: 'pointer',
                  padding: '7px 10px',
                  borderRadius: 'var(--tawn-radius-sm)',
                  fontSize: 13,
                  fontWeight: active === t.key ? 600 : 400,
                  color: active === t.key ? 'var(--tawn-lapis)' : 'var(--tawn-text-2)',
                  background: active === t.key ? 'var(--tawn-lapis-soft)' : 'transparent',
                  transition: 'background 0.12s',
                  userSelect: 'none',
                }}
              >
                {t.label}
              </div>
            ))}
          </div>
        )
      })}
    </nav>
  )
}

function PathList({ label, paths, setPaths }: { label: string; paths: string[]; setPaths: (p: string[]) => void }) {
  const [draft, setDraft] = useState('')
  const [picking, setPicking] = useState(false)

  async function pickFolder() {
    setPicking(true)
    try {
      const res = await fetch('/api/browse/folder')
      const data = await res.json()
      const p: string | null = data.path
      if (p && !paths.includes(p)) setPaths([...paths, p])
    } catch { /* ignore */ } finally {
      setPicking(false)
    }
  }

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--tawn-text-2)', marginBottom: 8 }}>{label}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8 }}>
        {paths.map((p) => (
          <div key={p} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <code style={{ flex: 1, fontSize: 13, fontFamily: 'var(--tawn-font-mono)' }}>{p}</code>
            <span onClick={() => setPaths(paths.filter((x) => x !== p))} style={{ color: 'var(--tawn-crit)', fontSize: 13, cursor: 'pointer' }}>remove</span>
          </div>
        ))}
        {paths.length === 0 && <span style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>none</span>}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Input mono value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="/path/to/add" style={{ flex: 1, minWidth: 0 }} onKeyDown={(e) => { if (e.key === 'Enter' && draft.trim()) { setPaths([...paths, draft.trim()]); setDraft('') } }} />
        <Button variant="secondary" onClick={() => { if (draft.trim()) { setPaths([...paths, draft.trim()]); setDraft('') } }}>add</Button>
        <Button variant="secondary" onClick={pickFolder} disabled={picking}>{picking ? '…' : 'browse'}</Button>
      </div>
    </div>
  )
}

function GrantsTab() {
  const [grants, setGrants] = useState<Grants | null>(null)
  const [status, setStatus] = useState('')
  const [loadError, setLoadError] = useState('')
  const [confirming, setConfirming] = useState(false)

  function load() {
    setLoadError('')
    getGrants().then(setGrants).catch((err: unknown) => {
      setLoadError(err instanceof Error ? err.message : String(err))
    })
  }

  useEffect(load, [])

  async function reviewAndConfirm() {
    setConfirming(true)
    try {
      const r = await confirmGrants()
      if (r.ok) load()
      else setLoadError(r.error || 'confirm failed')
    } catch (err: unknown) {
      setLoadError(err instanceof Error ? err.message : String(err))
    } finally {
      setConfirming(false)
    }
  }

  async function save() {
    if (!grants) return
    setStatus('saving…')
    try {
      await putGrants(grants)
      setStatus('saved')
    } catch (err: unknown) {
      setStatus(`error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  if (loadError) {
    return (
      <Card>
        <p style={{ fontSize: 13, color: 'var(--tawn-crit)', marginBottom: 10 }}>{loadError}</p>
        <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginBottom: 14, lineHeight: 1.5 }}>
          grants.yaml was changed outside the normal save flow. Review <code style={{ fontFamily: 'var(--tawn-font-mono)' }}>~/.tawn/grants.yaml</code> yourself, then confirm it below — or run <code style={{ fontFamily: 'var(--tawn-font-mono)' }}>tawn grant confirm</code> from a terminal.
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button onClick={reviewAndConfirm} disabled={confirming}>{confirming ? 'confirming…' : "I've reviewed it — confirm"}</Button>
          <Button variant="secondary" onClick={load}>retry</Button>
        </div>
      </Card>
    )
  }

  if (!grants) return <Card><p style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>loading…</p></Card>

  return (
    <Card>
      <PathList label="read paths" paths={grants.read} setPaths={(p) => setGrants({ ...grants, read: p })} />
      <PathList label="write paths" paths={grants.write} setPaths={(p) => setGrants({ ...grants, write: p })} />
      <Checkbox label="system awareness" hint="full-system context, per-session opt-in" checked={grants.system} onChange={(e) => setGrants({ ...grants, system: e.target.checked })} />
      <div style={{ marginTop: 20, display: 'flex', gap: 8, alignItems: 'center' }}>
        <Button onClick={save}>save grants</Button>
        {status && <span style={{ fontSize: 12, color: 'var(--tawn-text-2)', fontFamily: 'var(--tawn-font-mono)' }}>{status}</span>}
      </div>
    </Card>
  )
}

function PersonalityTab() {
  const [profile, setProfile] = useState<Record<string, string>>({})
  const [tone, setTone] = useState('Direct, technical, unembellished. Skip the pep talk.')
  const [status, setStatus] = useState('')

  useEffect(() => { getProfile().then(setProfile).catch(() => {}) }, [])

  async function save() {
    setStatus('saving…')
    try {
      await putProfile({ name: profile.name || '', role: profile.role || '', focus: profile.focus || '', extra: {} })
      setStatus('saved')
    } catch (err: unknown) {
      setStatus(`error: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  return (
    <Card>
      <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginBottom: 16, lineHeight: 1.5 }}>
        Identity (below, factual) ships the same to every model provider. Personality — learned tone — is separate, bounded, and always correctable.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 12, color: 'var(--tawn-text-2)', marginBottom: 6 }}>name</div>
          <Input value={profile.name || ''} onChange={(e) => setProfile({ ...profile, name: e.target.value })} placeholder="your name" />
        </div>
        <div>
          <div style={{ fontSize: 12, color: 'var(--tawn-text-2)', marginBottom: 6 }}>role</div>
          <Input value={profile.role || ''} onChange={(e) => setProfile({ ...profile, role: e.target.value })} placeholder="your role" />
        </div>
      </div>
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 12, color: 'var(--tawn-text-2)', marginBottom: 6 }}>current focus</div>
        <Input value={profile.focus || ''} onChange={(e) => setProfile({ ...profile, focus: e.target.value })} placeholder="what you're working on right now" />
      </div>
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: 'var(--tawn-text-2)', marginBottom: 6 }}>how tawn should sound</div>
        <Textarea rows={3} value={tone} onChange={(e) => setTone(e.target.value)} />
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <Button onClick={save}>save profile</Button>
        {status && <span style={{ fontSize: 12, color: 'var(--tawn-text-2)', fontFamily: 'var(--tawn-font-mono)' }}>{status}</span>}
      </div>
    </Card>
  )
}

const KNOWN_DOMAINS = ['work', 'wealth', 'research', 'academic', 'hobby'] as const
type KnownDomain = typeof KNOWN_DOMAINS[number]

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <span
      onClick={() => onChange(!checked)}
      style={{ display: 'inline-flex', alignItems: 'center', width: 36, height: 20, borderRadius: 999, background: checked ? 'var(--tawn-lapis)' : 'var(--tawn-line-strong)', cursor: 'pointer', padding: 2, transition: 'background 0.2s', flexShrink: 0 }}
    >
      <span style={{ width: 16, height: 16, borderRadius: '50%', background: '#fff', transform: checked ? 'translateX(16px)' : 'translateX(0)', transition: 'transform 0.2s' }} />
    </span>
  )
}

function DomainsTab() {
  const navigate = useNavigate()
  const [domains, setDomains] = useState<DomainRow[]>([])
  const [toggling, setToggling] = useState<string | null>(null)

  useEffect(() => { getDomains().then(setDomains).catch(() => {}) }, [])

  async function toggle(d: DomainRow) {
    setToggling(d.name)
    try {
      if (d.nav) await disableDomain(d.name)
      else await enableDomain(d.name)
      setDomains((prev) => prev.map((x) => x.name === d.name ? { ...x, nav: !x.nav } : x))
    } catch { /* ignore */ } finally {
      setToggling(null)
    }
  }

  return (
    <Card padded={false}>
      <div style={{ padding: '16px 20px 0' }}>
        {domains.map((d) => {
          const key = KNOWN_DOMAINS.includes(d.name as KnownDomain) ? d.name as KnownDomain : undefined
          return (
            <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 0', borderBottom: '1px solid var(--tawn-line)' }}>
              <Badge domain={key}>{d.label}</Badge>
              <span style={{ flex: 1, fontSize: 12, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>{d.name}</span>
              <span style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginRight: 4 }}>{d.nav ? 'enabled' : 'disabled'}</span>
              <Toggle checked={d.nav} onChange={() => !toggling && toggle(d)} />
            </div>
          )
        })}
        {domains.length === 0 && <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', padding: '16px 0' }}>no domains configured yet</p>}
      </div>
      <div style={{ padding: '16px 20px 20px' }}>
        <Button variant="secondary" onClick={() => navigate('/domain/create')}>+ create a new domain</Button>
      </div>
    </Card>
  )
}

const PROVIDERS = ['anthropic', 'openai', 'gemini', 'deepseek', 'openrouter', 'ollama']

const OLLAMA_POPULAR = ['llama3.2', 'llama3.1', 'mistral', 'gemma3', 'qwen2.5', 'phi4', 'deepseek-r1', 'codellama']

interface EmbedCandidate { id: string; dims: number; provider: string; label: string }

function ModelsTab() {
  const [models, setModels] = useState<ModelRow[]>([])
  const [keyStates, setKeyStates] = useState<Record<string, string>>({})
  const [provider, setProvider] = useState(PROVIDERS[0])
  const [apiKey, setApiKey] = useState('')
  const [keyMsg, setKeyMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [ollamaModel, setOllamaModel] = useState('')
  const [ollamaMsg, setOllamaMsg] = useState('')
  const [pulling, setPulling] = useState(false)
  const [embedCurrent, setEmbedCurrent] = useState('')
  const [embedCandidates, setEmbedCandidates] = useState<EmbedCandidate[]>([])
  const [embedMsg, setEmbedMsg] = useState('')
  const [embedBusy, setEmbedBusy] = useState(false)

  function loadEmbed() {
    fetch('/api/models/embed').then((r) => r.json()).then((d: { current: string; candidates: EmbedCandidate[] }) => {
      setEmbedCurrent(d.current || '')
      setEmbedCandidates(d.candidates)
    }).catch(() => {})
  }

  useEffect(() => {
    getAllModels().then(setModels).catch(() => {})
    PROVIDERS.forEach((p) => getKeyStatus(p).then((r) => setKeyStates((s) => ({ ...s, [p]: r.status }))).catch(() => {}))
    loadEmbed()
  }, [])

  async function selectEmbedModel(id: string) {
    setEmbedBusy(true)
    setEmbedMsg(`testing ${id}…`)
    try {
      const r = await fetch('/api/models/embed', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: id }),
      })
      const d = await r.json() as { ok: boolean; model?: string; dims?: number; error?: string }
      if (d.ok) {
        setEmbedCurrent(d.model ?? id)
        setEmbedMsg(`✓ ${d.model} (${d.dims} dims) — run compile to rebuild embeddings`)
      } else {
        setEmbedMsg(`✗ ${d.error}`)
      }
    } catch (err) {
      setEmbedMsg(`error: ${err}`)
    } finally {
      setEmbedBusy(false)
    }
  }

  async function saveKey(e: React.FormEvent) {
    e.preventDefault()
    if (!apiKey.trim()) return
    setBusy(true)
    try {
      await postKey(provider, apiKey.trim())
      setKeyStates((s) => ({ ...s, [provider]: 'set' }))
      setKeyMsg(`${provider} key stored`)
      setApiKey('')
      getAllModels().then(setModels).catch(() => {})
    } catch (err: unknown) {
      setKeyMsg(`error: ${err instanceof Error ? err.message : String(err)}`)
    } finally { setBusy(false) }
  }

  async function pullOllama() {
    const name = ollamaModel.trim()
    if (!name) return
    setPulling(true)
    setOllamaMsg(`pulling ${name}…`)
    try {
      const res = await fetch('/api/update/ollama-pull', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: name }),
      })
      const data = await res.json()
      if (data.ok) {
        setOllamaMsg(`${name} installed — refresh to see it in the list`)
        setOllamaModel('')
        getAllModels().then(setModels).catch(() => {})
      } else {
        setOllamaMsg(`error: ${data.error || 'pull failed'}`)
      }
    } catch (err: unknown) {
      setOllamaMsg(`error: ${err instanceof Error ? err.message : String(err)}`)
    } finally { setPulling(false) }
  }

  const byLocality = (loc: string) => models.filter((m) => m.locality === loc)
  const cloud = byLocality('cloud')
  const local = byLocality('local')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* available models */}
      <Card padded={false}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--tawn-line)' }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>available now</div>
        </div>
        {models.length === 0 ? (
          <div style={{ padding: '20px', fontSize: 13, color: 'var(--tawn-text-2)' }}>no models — add a cloud key below or install an Ollama model</div>
        ) : (
          <>
            {cloud.map((m) => (
              <div key={m.target} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 20px', borderBottom: '1px solid var(--tawn-line)' }}>
                <span style={{ fontSize: 13, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text)', flex: 1 }}>{m.model}</span>
                <Badge tone="neutral">{m.provider}</Badge>
                <Badge tone="neutral">cloud</Badge>
              </div>
            ))}
            {local.map((m) => (
              <div key={m.target} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 20px', borderBottom: '1px solid var(--tawn-line)' }}>
                <span style={{ fontSize: 13, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text)', flex: 1 }}>{m.model}</span>
                <Badge tone="neutral">{m.provider}</Badge>
                <Badge status="good">local</Badge>
              </div>
            ))}
          </>
        )}
      </Card>

      {/* provider key status */}
      <Card>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>provider keys</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
          {PROVIDERS.map((p) => (
            <span key={p} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, fontFamily: 'var(--tawn-font-mono)', border: '1px solid var(--tawn-line)', borderRadius: 999, padding: '3px 9px', color: keyStates[p] === 'set' ? 'var(--tawn-good)' : 'var(--tawn-text-3)' }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: keyStates[p] === 'set' ? 'var(--tawn-good)' : 'var(--tawn-line-strong)' }} />
              {p}
            </span>
          ))}
        </div>
        <form onSubmit={saveKey} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <select value={provider} onChange={(e) => setProvider(e.target.value)} style={{ fontSize: 13, fontFamily: 'var(--tawn-font-mono)', padding: '8px 10px', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', background: 'var(--tawn-raised)', color: 'var(--tawn-text)', flexShrink: 0 }}>
            {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <Input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-…" mono style={{ flex: 1, minWidth: 160 }} />
          <Button type="submit" disabled={busy || !apiKey.trim()}>store key</Button>
        </form>
        {keyMsg && <div style={{ marginTop: 8, fontSize: 12, fontFamily: 'var(--tawn-font-mono)', color: keyMsg.startsWith('error') ? 'var(--tawn-crit)' : 'var(--tawn-good)' }}>{keyMsg}</div>}
      </Card>

      {/* install local model via Ollama */}
      <Card>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>install local model (ollama)</div>
        <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginBottom: 12 }}>Requires Ollama to be running locally. Pull any model from <code style={{ fontFamily: 'var(--tawn-font-mono)', fontSize: 11 }}>ollama.com/library</code>.</p>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
          {OLLAMA_POPULAR.map((m) => (
            <span
              key={m}
              onClick={() => setOllamaModel(m)}
              style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', border: '1px solid var(--tawn-line)', borderRadius: 999, padding: '3px 8px', cursor: 'pointer', background: ollamaModel === m ? 'var(--tawn-lapis-soft)' : 'transparent', color: ollamaModel === m ? 'var(--tawn-lapis)' : 'var(--tawn-text-3)', transition: 'background 0.12s' }}
            >
              {m}
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Input mono value={ollamaModel} onChange={(e) => setOllamaModel(e.target.value)} placeholder="llama3.2" style={{ flex: 1 }} />
          <Button onClick={pullOllama} disabled={pulling || !ollamaModel.trim()}>{pulling ? 'pulling…' : 'pull & install'}</Button>
        </div>
        {ollamaMsg && <div style={{ marginTop: 8, fontSize: 12, fontFamily: 'var(--tawn-font-mono)', color: ollamaMsg.startsWith('error') ? 'var(--tawn-crit)' : 'var(--tawn-text-2)' }}>{ollamaMsg}</div>}
      </Card>

      {/* Embedding model selection */}
      <Card>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>embedding model</div>
        <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginBottom: 14 }}>
          Used for semantic recall. Local (Ollama) is free; cloud options cost per token.
          {embedCurrent && <span style={{ marginLeft: 8, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-good)' }}>active: {embedCurrent}</span>}
          {!embedCurrent && <span style={{ marginLeft: 8, color: 'var(--tawn-warn)' }}>not set — recall uses keyword search only</span>}
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {embedCandidates.map((c) => (
            <div
              key={c.id}
              onClick={() => !embedBusy && selectEmbedModel(c.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
                border: `1px solid ${embedCurrent === c.id ? 'var(--tawn-lapis)' : 'var(--tawn-line)'}`,
                borderRadius: 8, cursor: embedBusy ? 'default' : 'pointer',
                background: embedCurrent === c.id ? 'var(--tawn-lapis-soft)' : 'var(--tawn-raised)',
              }}
            >
              <span style={{ fontSize: 13, fontFamily: 'var(--tawn-font-mono)', color: embedCurrent === c.id ? 'var(--tawn-lapis)' : 'var(--tawn-text)', fontWeight: embedCurrent === c.id ? 600 : 400, flex: 1 }}>{c.label}</span>
              <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)' }}>{c.dims}d</span>
              <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: c.provider === 'ollama' ? 'var(--tawn-good)' : 'var(--tawn-text-3)' }}>{c.provider}</span>
              {embedCurrent === c.id && <span style={{ fontSize: 11, color: 'var(--tawn-good)' }}>✓</span>}
            </div>
          ))}
        </div>
        {embedMsg && <div style={{ marginTop: 10, fontSize: 12, fontFamily: 'var(--tawn-font-mono)', color: embedMsg.startsWith('✗') || embedMsg.startsWith('error') ? 'var(--tawn-crit)' : 'var(--tawn-text-2)' }}>{embedMsg}</div>}
      </Card>
    </div>
  )
}

type ExportEntry = { label: string; desc: string; downloads: { label: string; url: string; filename: string }[] }

const EXPORTS: ExportEntry[] = [
  {
    label: 'audit log',
    desc: 'chain-verified, tamper-evident event log.',
    downloads: [
      { label: 'JSON', url: '/api/audit/export?format=json', filename: 'tawn-audit.json' },
      { label: 'CSV', url: '/api/audit/export?format=csv', filename: 'tawn-audit.csv' },
    ],
  },
  {
    label: 'memory (JSONL)',
    desc: 'all compiled memory chunks as newline-delimited JSON.',
    downloads: [{ label: 'download', url: '/api/export/download?format=jsonl', filename: 'tawn-export.jsonl' }],
  },
  {
    label: 'full bundle',
    desc: 'wiki markdown + entity graph + JSONL, zipped.',
    downloads: [{ label: 'download zip', url: '/api/export/download?format=zip', filename: 'tawn-export.zip' }],
  },
]

function _triggerDownload(url: string, filename: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

function ExportsTab() {
  return (
    <Card padded={false}>
      <div style={{ padding: '4px 20px 20px' }}>
        {EXPORTS.map((e) => (
          <div key={e.label} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '16px 0', borderBottom: '1px solid var(--tawn-line)' }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{e.label}</div>
              <div style={{ fontSize: 12, color: 'var(--tawn-text-2)', marginTop: 2 }}>{e.desc}</div>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {e.downloads.map((d) => (
                <Button key={d.label} size="sm" variant="secondary" onClick={() => _triggerDownload(d.url, d.filename)}>
                  {d.label}
                </Button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function IntegrationsTab() {
  const navigate = useNavigate()
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <Card style={{ cursor: 'pointer' }} onClick={() => navigate('/agents')}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>connect tawn to your agents →</div>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', lineHeight: 1.5 }}>Per-agent MCP config snippets — Claude Code, Cursor, Gemini CLI, and a plain AGENTS.md block.</p>
      </Card>
      <Card>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>MCP skill factory</div>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', lineHeight: 1.5, marginBottom: 10 }}>Author skills that project to every agent's AGENTS.md. Coming in Stage 9.</p>
        <Badge tone="neutral">stage 9</Badge>
      </Card>
      <Card style={{ cursor: 'pointer' }} onClick={() => navigate('/setup')}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>model providers & setup →</div>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', lineHeight: 1.5 }}>Configure Anthropic, OpenAI, Ollama and other providers. Run the setup wizard.</p>
      </Card>
    </div>
  )
}

interface UpdateInfo {
  method: string
  current: string
  latest: string | null
  update_available: boolean
  last_check: number | null
  last_update: number | null
  running: boolean
  error: string | null
}

function UpdatesTab() {
  const [info, setInfo] = useState<UpdateInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const [msg, setMsg] = useState('')

  async function load() {
    setLoading(true)
    try {
      const res = await fetch('/api/update/status')
      setInfo(await res.json())
    } catch { /* ignore */ } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  async function doUpdate() {
    setTriggering(true)
    setMsg('')
    try {
      const res = await fetch('/api/update/trigger', { method: 'POST' })
      const data = await res.json()
      setMsg(data.ok ? `update started (method: ${data.method}) — restart tawn when done` : `error: ${data.error}`)
    } catch (err: unknown) {
      setMsg(`error: ${err instanceof Error ? err.message : String(err)}`)
    } finally { setTriggering(false) }
  }

  function fmtTime(ts: number | null) {
    if (!ts) return '—'
    return new Date(ts * 1000).toLocaleString()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>tawn version</div>
        {loading ? (
          <p style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>checking…</p>
        ) : info ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: 11, color: 'var(--tawn-text-3)', marginBottom: 2 }}>installed</div>
                <code style={{ fontFamily: 'var(--tawn-font-mono)', fontSize: 14, fontWeight: 700 }}>{info.current}</code>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--tawn-text-3)', marginBottom: 2 }}>latest</div>
                <code style={{ fontFamily: 'var(--tawn-font-mono)', fontSize: 14, fontWeight: 700, color: info.update_available ? 'var(--tawn-warn)' : 'var(--tawn-good)' }}>{info.latest ?? '—'}</code>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--tawn-text-3)', marginBottom: 2 }}>install method</div>
                <code style={{ fontFamily: 'var(--tawn-font-mono)', fontSize: 13 }}>{info.method}</code>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 20, fontSize: 12, color: 'var(--tawn-text-3)' }}>
              <span>last check: {fmtTime(info.last_check)}</span>
              <span>last update: {fmtTime(info.last_update)}</span>
            </div>
            {info.error && <div style={{ fontSize: 12, color: 'var(--tawn-crit)', fontFamily: 'var(--tawn-font-mono)' }}>error: {info.error}</div>}
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 6 }}>
              <Button onClick={doUpdate} disabled={triggering || info.running}>
                {info.running ? 'updating…' : 'update now'}
              </Button>
              <Button variant="secondary" onClick={load}>refresh</Button>
            </div>
            {msg && <div style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', color: msg.startsWith('error') ? 'var(--tawn-crit)' : 'var(--tawn-text-2)' }}>{msg}</div>}
          </div>
        ) : (
          <p style={{ fontSize: 13, color: 'var(--tawn-crit)' }}>could not load update status</p>
        )}
      </Card>
      <Card>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>automatic updates</div>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', lineHeight: 1.55 }}>
          Tawn checks for updates daily at 23:55 and reinstalls automatically when the web server is running. After update, restart the web server to use the new version.
        </p>
        <div style={{ marginTop: 10, fontSize: 12, color: 'var(--tawn-text-3)' }}>
          Manual check: <code style={{ fontFamily: 'var(--tawn-font-mono)' }}>tawn update --check</code>
          {' · '}
          Manual update: <code style={{ fontFamily: 'var(--tawn-font-mono)' }}>tawn update</code>
        </div>
      </Card>
    </div>
  )
}

function DatabaseTab() {
  const [stats, setStats] = useState<ChunkStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [confirm, setConfirm] = useState<'imports' | 'history' | 'all' | null>(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  async function load() {
    setLoading(true)
    try { setStats(await getChunkStats()) } catch { /* ignore */ } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  async function doClear(type: 'imports' | 'history' | 'all') {
    setBusy(true)
    setMsg('')
    try {
      const r = await deleteChunks(type)
      setMsg(`deleted ${r.deleted} chunks`)
      await load()
    } catch (err) {
      setMsg(`error: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
      setConfirm(null)
    }
  }

  async function rebuild() {
    setBusy(true)
    setMsg('clearing all chunks…')
    try {
      await deleteChunks('all')
      setMsg('rebuilding index…')
      await postCompile()
      setMsg('rebuild complete')
      await load()
    } catch (err) {
      setMsg(`error: ${err instanceof Error ? err.message : String(err)}`)
    } finally { setBusy(false) }
  }

  const StatRow = ({ label, value, sub }: { label: string; value: number; sub?: string }) => (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '8px 0', borderBottom: '1px solid var(--tawn-line)' }}>
      <span style={{ flex: 1, fontSize: 13, color: 'var(--tawn-text-2)' }}>{label}</span>
      {sub && <span style={{ fontSize: 11, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>{sub}</span>}
      <span style={{ fontSize: 15, fontWeight: 600, fontFamily: 'var(--tawn-font-mono)', minWidth: 48, textAlign: 'right' }}>{value.toLocaleString()}</span>
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Card>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>chunk index</div>
        {loading ? (
          <p style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>loading…</p>
        ) : stats ? (
          <>
            {stats.embed_model ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0', borderBottom: '1px solid var(--tawn-line)' }}>
                <span style={{ flex: 1, fontSize: 13, color: 'var(--tawn-text-2)' }}>active embedder</span>
                <span style={{ fontSize: 13, fontWeight: 600, fontFamily: 'var(--tawn-font-mono)' }}>{stats.embed_model}</span>
                <span style={{ fontSize: 11, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>{stats.embed_dims}d</span>
              </div>
            ) : (
              <div style={{ padding: '8px 0', borderBottom: '1px solid var(--tawn-line)' }}>
                <span style={{ fontSize: 13, color: 'var(--tawn-warn)' }}>no embed model locked yet — set one in Models tab</span>
              </div>
            )}
            <StatRow label="total chunks" value={stats.total} />
            <StatRow label="with embeddings" value={stats.with_embeddings} sub={stats.total ? `${Math.round(stats.with_embeddings / stats.total * 100)}%` : undefined} />
            <StatRow label="agent memory" value={stats.by_type['agent-memory']} sub="project context" />
            <StatRow label="raw notes" value={stats.by_type.raw} sub="your notes" />
            <StatRow label="chat history" value={stats.by_type.history} />
            <StatRow label="fed imports" value={stats.by_type.imports} sub="conversation exports" />
            <div style={{ marginTop: 12 }}>
              <Button size="sm" variant="secondary" onClick={load} disabled={loading}>refresh stats</Button>
            </div>
          </>
        ) : (
          <p style={{ fontSize: 13, color: 'var(--tawn-crit)' }}>failed to load stats</p>
        )}
      </Card>

      <Card>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>clear chunks</div>
        <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginBottom: 16, lineHeight: 1.5 }}>
          Removes chunks from the index. Run compile after to reindex surviving files.
        </p>

        {[
          { type: 'imports' as const, label: 'clear imported conversations', desc: 'Removes conversation export chunks (federation imports). Keeps notes, agent memory, and chat history.' },
          { type: 'history' as const, label: 'clear chat history chunks', desc: 'Removes indexed chat session chunks. Raw chat files are not deleted.' },
          { type: 'all' as const, label: 'clear all chunks', desc: 'Wipes the entire index. Run compile to rebuild.', danger: true },
        ].map(({ type, label, desc, danger }) => (
          <div key={type} style={{ marginBottom: 16, padding: '14px 16px', border: `1px solid ${danger ? 'var(--tawn-crit)' : 'var(--tawn-line)'}`, borderRadius: 8, opacity: danger ? 0.9 : 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, color: danger ? 'var(--tawn-crit)' : 'var(--tawn-text)' }}>{label}</div>
            <div style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginBottom: 10 }}>{desc}</div>
            {confirm === type ? (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ fontSize: 12, color: 'var(--tawn-crit)' }}>are you sure?</span>
                <Button size="sm" variant={danger ? 'danger' : 'secondary'} onClick={() => doClear(type)} disabled={busy}>confirm</Button>
                <Button size="sm" variant="secondary" onClick={() => setConfirm(null)} disabled={busy}>cancel</Button>
              </div>
            ) : (
              <Button size="sm" variant={danger ? 'danger' : 'secondary'} onClick={() => setConfirm(type)} disabled={busy}>{label}</Button>
            )}
          </div>
        ))}

        {msg && <div style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', marginTop: 8, color: msg.startsWith('error') ? 'var(--tawn-crit)' : 'var(--tawn-good)' }}>{msg}</div>}
      </Card>

      <Card>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>rebuild index</div>
        <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginBottom: 12, lineHeight: 1.5 }}>
          Clears all chunks then runs a full compile pass — regenerates embeddings, re-classifies domains, and reindexes everything from scratch.
        </p>
        <Button variant="danger" onClick={rebuild} disabled={busy}>{busy ? msg || 'working…' : 'clear + rebuild'}</Button>
      </Card>
    </div>
  )
}

const AUDIT_PAGE = 50

function AuditPanel() {
  const [data, setData] = useState<AuditPage>({ total: 0, entries: [] })
  const [offset, setOffset] = useState(0)
  const [intact, setIntact] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)
  const [verifying, setVerifying] = useState(false)

  function load(off: number) {
    setLoading(true)
    getAudit(AUDIT_PAGE, off)
      .then((d) => { setData(d); setOffset(off) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(0) }, [])

  async function verify() {
    setVerifying(true)
    try {
      const r = await verifyAudit()
      setIntact(r.intact)
    } catch {
      setIntact(false)
    } finally {
      setVerifying(false)
    }
  }

  const start = offset + 1
  const end = Math.min(offset + AUDIT_PAGE, data.total)

  const ACTOR_COLOR: Record<string, string> = {
    web: 'var(--tawn-lapis)', cli: 'var(--tawn-good)', chat: 'var(--tawn-warn)',
    mcp: 'var(--tawn-crit)', system: 'var(--tawn-text-3)',
  }

  return (
    <div>
      {/* toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        <span style={{ fontSize: 12, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)', marginRight: 4 }}>
          {data.total} entries
        </span>
        <Button size="sm" variant="secondary" onClick={verify} disabled={verifying}>
          {verifying ? 'verifying…' : 'verify chain'}
        </Button>
        <Button size="sm" variant="secondary" onClick={() => { const a = document.createElement('a'); a.href='/api/audit/export?format=json'; a.download='tawn-audit.json'; a.click() }}>
          export JSON
        </Button>
        <Button size="sm" variant="secondary" onClick={() => { const a = document.createElement('a'); a.href='/api/audit/export?format=csv'; a.download='tawn-audit.csv'; a.click() }}>
          export CSV
        </Button>
        {intact !== null && (
          <Badge status={intact ? 'good' : 'crit'}>
            {intact ? 'chain intact' : 'chain broken — possible tampering'}
          </Badge>
        )}
      </div>

      {/* table */}
      {loading ? (
        <div style={{ fontSize: 13, color: 'var(--tawn-text-2)', padding: '20px 0' }}>loading…</div>
      ) : data.entries.length === 0 ? (
        <div style={{ background: 'var(--tawn-raised)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', padding: '28px 20px', textAlign: 'center' }}>
          <div style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>no audit entries yet</div>
          <div style={{ fontSize: 12, color: 'var(--tawn-text-3)', marginTop: 4, fontFamily: 'var(--tawn-font-mono)' }}>entries appear when tawn records FS access, grant changes, or model calls</div>
        </div>
      ) : (
        <div style={{ border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: 'var(--tawn-surface)', borderBottom: '1px solid var(--tawn-line)' }}>
                  {['time', 'actor', 'op', 'target', 'ok', 'chain'].map((h) => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--tawn-text-2)', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.entries.map((e, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--tawn-line)', background: i % 2 === 0 ? 'transparent' : 'var(--tawn-raised)' }}>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', whiteSpace: 'nowrap' }}>
                      {e.ts.replace('T', ' ').slice(0, 19)}
                    </td>
                    <td style={{ padding: '8px 12px', whiteSpace: 'nowrap' }}>
                      <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: ACTOR_COLOR[e.actor || 'system'] || 'var(--tawn-text-3)' }}>
                        {e.actor || '—'}
                      </span>
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-lapis)', whiteSpace: 'nowrap' }}>
                      {e.op}
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--tawn-font-mono)', fontSize: 11, color: 'var(--tawn-text-2)', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={e.target}>
                      {e.target}
                    </td>
                    <td style={{ padding: '8px 12px' }}>
                      <Badge status={e.ok ? 'good' : 'crit'}>{e.ok ? 'ok' : 'fail'}</Badge>
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--tawn-font-mono)', fontSize: 11, color: 'var(--tawn-text-3)', whiteSpace: 'nowrap' }}>
                      {e.chain.slice(0, 10)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* pagination */}
          {data.total > AUDIT_PAGE && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderTop: '1px solid var(--tawn-line)', background: 'var(--tawn-surface)' }}>
              <Button size="sm" variant="secondary" onClick={() => load(Math.max(0, offset - AUDIT_PAGE))} disabled={offset === 0}>← prev</Button>
              <span style={{ fontSize: 12, color: 'var(--tawn-text-2)', fontFamily: 'var(--tawn-font-mono)' }}>
                {start}–{end} of {data.total}
              </span>
              <Button size="sm" variant="secondary" onClick={() => load(offset + AUDIT_PAGE)} disabled={offset + AUDIT_PAGE >= data.total}>next →</Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function Settings() {
  const [tab, setTab] = useState<Tab>('grants')
  const mobile = useIsMobile()
  return (
    <div style={{ background: 'var(--tawn-bg)', minHeight: '100vh' }}>
      <AppNav />
      <div style={{ maxWidth: 900, margin: '0 auto', padding: mobile ? '20px 16px 48px' : '32px 24px 64px' }}>
        <h1 style={{ fontSize: mobile ? 19 : 22, fontWeight: 700, marginBottom: 4 }}>settings</h1>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginBottom: mobile ? 18 : 28 }}>deny-all by default. every access is logged to the audit trail.</p>
        <div style={{ display: 'flex', flexDirection: mobile ? 'column' : 'row', gap: mobile ? 0 : 32, alignItems: mobile ? 'stretch' : 'flex-start' }}>
          <SideNav active={tab} setActive={setTab} mobile={mobile} />
          <div style={{ flex: 1, minWidth: 0 }}>
            {tab === 'grants' && <GrantsTab />}
            {tab === 'personality' && <PersonalityTab />}
            {tab === 'domains' && <DomainsTab />}
            {tab === 'models' && <ModelsTab />}
            {tab === 'exports' && <ExportsTab />}
            {tab === 'integrations' && <IntegrationsTab />}
            {tab === 'setup' && <SetupWizard />}
            {tab === 'database' && <DatabaseTab />}
            {tab === 'audit' && <AuditPanel />}
            {tab === 'logs' && <LogsPanel />}
            {tab === 'updates' && <UpdatesTab />}
          </div>
        </div>
      </div>
    </div>
  )
}
