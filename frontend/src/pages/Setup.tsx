import { FormEvent, useEffect, useState } from 'react'
import Layout from '../components/Layout'
import { Card, Button, Input, Select, Badge } from '../ds'
import { useErrors } from '../components/Errors'
import {
  postSetupInit,
  postSetupDb,
  postKey,
  getKeyStatus,
  getSetupHost,
  getSetupTunnel,
} from '../lib/api'

const PROVIDERS = ['anthropic', 'openai', 'gemini', 'deepseek', 'openrouter', 'ollama']

type StepState = 'idle' | 'running' | 'ok' | 'error'

function StepBadge({ state }: { state: StepState }) {
  if (state === 'idle') return null
  if (state === 'running') return <Badge tone="neutral">running…</Badge>
  if (state === 'ok') return <Badge status="good">done</Badge>
  return <Badge status="crit">failed</Badge>
}

function StepCard({ n, title, desc, children, state }: { n: string; title: string; desc: string; children: React.ReactNode; state: StepState }) {
  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-lapis)', fontWeight: 600 }}>{n}</span>
          <h2 style={{ fontSize: 15, fontWeight: 700 }}>{title}</h2>
        </div>
        <StepBadge state={state} />
      </div>
      <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginBottom: 14, lineHeight: 1.55 }}>{desc}</p>
      {children}
    </Card>
  )
}

function LogBox({ lines }: { lines: string[] }) {
  if (!lines.length) return null
  return (
    <div style={{ marginTop: 12, background: 'var(--tawn-raised)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', padding: '10px 14px' }}>
      {lines.map((l, i) => (
        <div key={i} style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', color: l.startsWith('error') ? 'var(--tawn-crit)' : 'var(--tawn-text-2)', lineHeight: 1.7 }}>{l}</div>
      ))}
    </div>
  )
}

export function SetupWizard() {
  const { report } = useErrors()
  const reportError = (e: unknown) => report(e instanceof Error ? e.message : String(e))
  const [busy, setBusy] = useState(false)
  const [log, setLog] = useState<string[]>([])
  const push = (line: string) => setLog((l) => [...l, line])

  // step states
  const [homeState, setHomeState] = useState<StepState>('idle')
  const [dbState, setDbState] = useState<StepState>('idle')
  const [hostState, setHostState] = useState<StepState>('idle')
  const [hostOk, setHostOk] = useState(false)
  const [tunnelUrl, setTunnelUrl] = useState<string | null>(null)
  const [tunnelActive, setTunnelActive] = useState(false)
  const [tunnelState, setTunnelState] = useState<StepState>('idle')

  // key management
  const [provider, setProvider] = useState(PROVIDERS[0])
  const [apiKey, setApiKey] = useState('')
  const [keyMsg, setKeyMsg] = useState('')
  const [keyStates, setKeyStates] = useState<Record<string, string>>({})
  const [keyState, setKeyState] = useState<StepState>('idle')

  useEffect(() => {
    getSetupHost().then((r) => { setHostOk(r.ok); setHostState(r.ok ? 'ok' : 'idle') }).catch(reportError)
    getSetupTunnel().then((r) => { setTunnelUrl(r.url); setTunnelActive(r.active); if (r.active) setTunnelState('ok') }).catch(reportError)
    PROVIDERS.forEach((p) => getKeyStatus(p).then((r) => setKeyStates((s) => ({ ...s, [p]: r.status }))).catch(reportError))
  }, [])

  async function runInit() {
    setBusy(true); setHomeState('running')
    try {
      const r = await postSetupInit()
      push(`home ready — ${r.created.length > 0 ? `created ${r.created.length} dirs` : 'already exists'}`)
      setHomeState('ok')
    } catch (e: unknown) {
      push(`error: ${e instanceof Error ? e.message : String(e)}`); setHomeState('error')
    } finally { setBusy(false) }
  }

  async function runDb() {
    setBusy(true); setDbState('running')
    try {
      const r = await postSetupDb()
      if (r.can_connect) { push('database ready'); setDbState('ok') }
      else { push(`database not ready: ${r.detail}`); setDbState('error') }
    } catch (e: unknown) {
      push(`error: ${e instanceof Error ? e.message : String(e)}`); setDbState('error')
    } finally { setBusy(false) }
  }

  async function checkHost() {
    setBusy(true); setHostState('running')
    try {
      const r = await getSetupHost()
      setHostOk(r.ok)
      if (r.ok) { push('tawn hostname resolves — tawn:8787 active'); setHostState('ok') }
      else { push(`hostname not set — add: 127.0.0.1  tawn  to /etc/hosts`); setHostState('error') }
    } catch (e: unknown) {
      push(`error: ${e instanceof Error ? e.message : String(e)}`); setHostState('error')
    } finally { setBusy(false) }
  }

  async function checkTunnel() {
    setBusy(true); setTunnelState('running')
    try {
      const r = await getSetupTunnel()
      setTunnelUrl(r.url); setTunnelActive(r.active)
      if (r.active && r.url) { push(`public url: ${r.url}`); setTunnelState('ok') }
      else { push('no active ngrok tunnel — run: ngrok http 8787'); setTunnelState('idle') }
    } catch (e: unknown) {
      push(`error: ${e instanceof Error ? e.message : String(e)}`); setTunnelState('error')
    } finally { setBusy(false) }
  }

  async function saveKey(e: FormEvent) {
    e.preventDefault()
    if (!apiKey.trim()) return
    setBusy(true); setKeyState('running')
    try {
      await postKey(provider, apiKey.trim())
      push(`key stored for ${provider}`)
      setApiKey('')
      setKeyMsg(`${provider} key stored`)
      setKeyStates((s) => ({ ...s, [provider]: 'set' }))
      setKeyState('ok')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setKeyMsg(`error: ${msg}`); setKeyState('error')
    } finally { setBusy(false) }
  }

  const port = 8787
  const localUrl = hostOk ? `http://tawn:${port}` : `http://127.0.0.1:${port}`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Step 1 — home */}
      <StepCard n="01" title="home directory" desc="Creates ~/.tawn/ and the capability skeleton. Safe to re-run." state={homeState}>
        <Button onClick={runInit} disabled={busy}>initialise home</Button>
      </StepCard>

      {/* Step 2 — database */}
      <StepCard n="02" title="database" desc="Checks PostgreSQL connectivity. Run 'tawn setup db' from the CLI for guided install instructions." state={dbState}>
        <Button onClick={runDb} disabled={busy} variant={dbState === 'ok' ? 'secondary' : 'primary'}>check database</Button>
      </StepCard>

      {/* Step 3 — hostname */}
      <StepCard
        n="03"
        title="hostname — tawn:8787"
        desc="Adds '127.0.0.1  tawn' to /etc/hosts so the web viewer is reachable at tawn:8787 instead of 127.0.0.1:8787. Requires sudo once."
        state={hostState}
      >
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: hostOk ? 'var(--tawn-good)' : 'var(--tawn-warn)', flexShrink: 0 }} />
            <code style={{ fontSize: 13, fontFamily: 'var(--tawn-font-mono)' }}>{localUrl}</code>
          </div>
        </div>
        {!hostOk && (
          <div style={{ marginBottom: 12, background: 'var(--tawn-raised)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', padding: '10px 14px' }}>
            <div style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-2)', marginBottom: 4 }}>add to /etc/hosts:</div>
            <div style={{ fontSize: 13, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text)' }}>127.0.0.1  tawn  # tawn web</div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 8 }}>
          <Button onClick={checkHost} disabled={busy} variant={hostOk ? 'secondary' : 'primary'}>check hostname</Button>
          {hostOk && <Button variant="secondary" onClick={() => window.open(localUrl, '_blank')}>open tawn:8787</Button>}
        </div>
      </StepCard>

      {/* Step 4 — keys */}
      <StepCard n="04" title="cloud api keys" desc="Optional — stored in the OS keyring, never in files or the ledger. Local models (Ollama) need no key." state={keyState}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
          {PROVIDERS.map((p) => (
            <span key={p} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: keyStates[p] === 'set' ? 'var(--tawn-good)' : 'var(--tawn-text-3)', border: '1px solid var(--tawn-line)', borderRadius: 999, padding: '3px 9px' }}>
              <span style={{ width: 5, height: 5, borderRadius: '50%', background: keyStates[p] === 'set' ? 'var(--tawn-good)' : 'var(--tawn-line-strong)' }} />
              {p}
            </span>
          ))}
        </div>
        <form onSubmit={saveKey} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Select value={provider} onChange={(e) => setProvider(e.target.value)} style={{ flexShrink: 0 }}>
            {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
          </Select>
          <Input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-…"
            mono
            style={{ flex: 1, minWidth: 160 }}
          />
          <Button type="submit" disabled={busy || !apiKey.trim()}>store key</Button>
        </form>
        {keyMsg && <div style={{ marginTop: 8, fontSize: 12, fontFamily: 'var(--tawn-font-mono)', color: keyMsg.startsWith('error') ? 'var(--tawn-crit)' : 'var(--tawn-good)' }}>{keyMsg}</div>}
      </StepCard>

      {/* Step 5 — public url / ngrok */}
      <StepCard
        n="05"
        title="public url (optional)"
        desc="Expose your twin over a public HTTPS URL using ngrok. Install ngrok, then run 'ngrok http 8787' in a terminal. You can share this URL with trusted collaborators — they'll access your twin's web viewer remotely."
        state={tunnelState}
      >
        {tunnelActive && tunnelUrl ? (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>public url</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--tawn-good)' }} />
              <a href={tunnelUrl} target="_blank" rel="noreferrer" style={{ fontSize: 13, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-lapis)' }}>{tunnelUrl}</a>
            </div>
            <div style={{ marginTop: 12, background: 'var(--tawn-raised)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', padding: '10px 14px' }}>
              <div style={{ fontSize: 12, color: 'var(--tawn-text-2)', marginBottom: 6, lineHeight: 1.5 }}>
                Share this URL with trusted collaborators. Anyone with the link can access your twin's web viewer — only share with people you trust.
              </div>
              <Button size="sm" variant="secondary" onClick={() => navigator.clipboard?.writeText(tunnelUrl).catch(reportError)}>copy url</Button>
            </div>
          </div>
        ) : (
          <div style={{ marginBottom: 12, background: 'var(--tawn-raised)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', padding: '10px 14px' }}>
            <div style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-2)', marginBottom: 4 }}>start a tunnel:</div>
            <div style={{ fontSize: 13, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text)' }}>ngrok http 8787</div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 8 }}>
          <Button onClick={checkTunnel} disabled={busy} variant="secondary">
            {tunnelActive ? 'refresh url' : 'check for tunnel'}
          </Button>
          {!tunnelActive && (
            <a href="https://ngrok.com/download" target="_blank" rel="noreferrer" style={{ display: 'inline-flex', alignItems: 'center', fontSize: 13, fontWeight: 600, color: 'var(--tawn-text-2)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', padding: '8px 14px', background: 'var(--tawn-raised)', textDecoration: 'none' }}>
              get ngrok →
            </a>
          )}
        </div>
      </StepCard>

      <LogBox lines={log} />
    </div>
  )
}

export default function Setup() {
  return (
    <Layout narrow>
      <h1 style={{ fontFamily: 'var(--tawn-font-display)', fontWeight: 700, fontSize: 24, letterSpacing: '-0.02em', marginBottom: 4 }}>setup</h1>
      <p style={{ color: 'var(--tawn-text-2)', marginBottom: 24, fontSize: 13 }}>safe to re-run at any time. steps are independent.</p>
      <SetupWizard />
    </Layout>
  )
}
