import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppNav from '../components/AppNav'
import { Card, Input, Textarea, Button, Checkbox, Badge } from '../ds'
import { getGrants, putGrants, getProfile, putProfile, getDomains, getAllModels, enableDomain, disableDomain, getKeyStatus, postKey, type Grants, type DomainRow, type ModelRow } from '../lib/api'
import { SetupWizard } from './Setup'
import { LogsPanel } from './Logs'
import { AuditPanel } from './Audit'

type Tab = 'grants' | 'personality' | 'domains' | 'models' | 'exports' | 'integrations' | 'setup' | 'audit' | 'logs' | 'updates'

const TABS: { key: Tab; label: string; group: string }[] = [
  { key: 'grants', label: 'grants', group: 'privacy' },
  { key: 'personality', label: 'personality', group: 'privacy' },
  { key: 'domains', label: 'domains', group: 'system' },
  { key: 'models', label: 'models', group: 'system' },
  { key: 'exports', label: 'exports', group: 'data' },
  { key: 'integrations', label: 'integrations', group: 'data' },
  { key: 'setup', label: 'setup', group: 'admin' },
  { key: 'audit', label: 'audit log', group: 'admin' },
  { key: 'logs', label: 'server logs', group: 'admin' },
  { key: 'updates', label: 'updates', group: 'admin' },
]

const GROUPS = ['privacy', 'system', 'data', 'admin']

function SideNav({ active, setActive }: { active: Tab; setActive: (t: Tab) => void }) {
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

  useEffect(() => { getGrants().then(setGrants).catch(() => {}) }, [])

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

export default function Settings() {
  const [tab, setTab] = useState<Tab>('grants')
  return (
    <div style={{ background: 'var(--tawn-bg)', minHeight: '100vh' }}>
      <AppNav />
      <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 24px 64px' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>settings</h1>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginBottom: 28 }}>deny-all by default. every access is logged to the audit trail.</p>
        <div style={{ display: 'flex', gap: 32, alignItems: 'flex-start' }}>
          <SideNav active={tab} setActive={setTab} />
          <div style={{ flex: 1, minWidth: 0 }}>
            {tab === 'grants' && <GrantsTab />}
            {tab === 'personality' && <PersonalityTab />}
            {tab === 'domains' && <DomainsTab />}
            {tab === 'models' && <ModelsTab />}
            {tab === 'exports' && <ExportsTab />}
            {tab === 'integrations' && <IntegrationsTab />}
            {tab === 'setup' && <SetupWizard />}
            {tab === 'audit' && <AuditPanel />}
            {tab === 'logs' && <LogsPanel />}
            {tab === 'updates' && <UpdatesTab />}
          </div>
        </div>
      </div>
    </div>
  )
}
