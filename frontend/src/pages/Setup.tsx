import { useState } from 'react'
import Layout from '../components/Layout'
import { postSetupInit, postSetupDb, postKey } from '../lib/api'

const PROVIDERS = ['anthropic', 'openai', 'gemini', 'deepseek']

export default function Setup() {
  const [log, setLog] = useState<string[]>([])
  const [provider, setProvider] = useState(PROVIDERS[0])
  const [apiKey, setApiKey] = useState('')
  const [keyMsg, setKeyMsg] = useState('')
  const [busy, setBusy] = useState(false)

  async function runInit() {
    setBusy(true)
    try {
      const r = await postSetupInit()
      setLog((l) => [...l, `home ready — created ${r.created.length} dirs`])
    } catch (e: unknown) {
      setLog((l) => [...l, `error: ${e instanceof Error ? e.message : String(e)}`])
    } finally {
      setBusy(false)
    }
  }

  async function runDb() {
    setBusy(true)
    try {
      const r = await postSetupDb()
      setLog((l) => [...l, r.can_connect ? 'database ready' : `database not ready: ${r.detail}`])
    } catch (e: unknown) {
      setLog((l) => [...l, `error: ${e instanceof Error ? e.message : String(e)}`])
    } finally {
      setBusy(false)
    }
  }

  async function saveKey(e: React.FormEvent) {
    e.preventDefault()
    if (!apiKey.trim()) return
    setBusy(true)
    try {
      await postKey(provider, apiKey.trim())
      setKeyMsg(`key stored for ${provider}`)
      setApiKey('')
    } catch (e: unknown) {
      setKeyMsg(`error: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  const inputStyle = {
    border: '1px solid var(--tawn-line)',
    borderRadius: 'var(--r-sm)',
    padding: '6px 10px',
    background: 'var(--tawn-raised)',
    color: 'var(--tawn-text)',
    fontSize: 'var(--sz-sm)',
    fontFamily: 'var(--tawn-font-body)',
  } as const

  const btnStyle = {
    padding: '7px 16px',
    background: 'var(--tawn-lapis)',
    color: '#fff',
    border: 'none',
    borderRadius: 'var(--r-sm)',
    cursor: busy ? 'not-allowed' : 'pointer',
    fontWeight: 600,
    opacity: busy ? 0.5 : 1,
    fontSize: 'var(--sz-sm)',
  } as const

  return (
    <Layout narrow>
      <h1 style={{ fontSize: 'var(--sz-xl)', fontWeight: 700, marginBottom: 8 }}>setup</h1>
      <p style={{ color: 'var(--tawn-text-2)', marginBottom: 28, fontSize: 'var(--sz-sm)' }}>
        Safe to re-run at any time.
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

        <section style={{ border: '1px solid var(--tawn-line)', borderRadius: 'var(--r)', padding: '14px 18px' }}>
          <h2 style={{ fontSize: 'var(--sz-sm)', fontWeight: 600, marginBottom: 8 }}>1. Home directory</h2>
          <p style={{ fontSize: 'var(--sz-sm)', color: 'var(--tawn-text-2)', marginBottom: 10 }}>
            Creates <code>~/.tawn/</code> and the capability skeleton.
          </p>
          <button onClick={runInit} disabled={busy} style={btnStyle}>Initialise</button>
        </section>

        <section style={{ border: '1px solid var(--tawn-line)', borderRadius: 'var(--r)', padding: '14px 18px' }}>
          <h2 style={{ fontSize: 'var(--sz-sm)', fontWeight: 600, marginBottom: 8 }}>2. Database</h2>
          <p style={{ fontSize: 'var(--sz-sm)', color: 'var(--tawn-text-2)', marginBottom: 10 }}>
            Sets up Postgres. Prints install instructions if not running.
          </p>
          <button onClick={runDb} disabled={busy} style={btnStyle}>Set up database</button>
        </section>

        <section style={{ border: '1px solid var(--tawn-line)', borderRadius: 'var(--r)', padding: '14px 18px' }}>
          <h2 style={{ fontSize: 'var(--sz-sm)', fontWeight: 600, marginBottom: 8 }}>3. Cloud API key</h2>
          <p style={{ fontSize: 'var(--sz-sm)', color: 'var(--tawn-text-2)', marginBottom: 10 }}>
            Optional. Stored in OS keyring, never in files.
          </p>
          <form onSubmit={saveKey} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              style={inputStyle}
            >
              {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-…"
              style={{ ...inputStyle, flex: 1, minWidth: 160, fontFamily: 'var(--tawn-font-mono)' }}
            />
            <button type="submit" disabled={busy || !apiKey.trim()} style={btnStyle}>Store key</button>
          </form>
          {keyMsg && <p style={{ fontSize: 'var(--sz-sm)', color: 'var(--tawn-good)', marginTop: 8 }}>{keyMsg}</p>}
        </section>

        {log.length > 0 && (
          <section style={{ border: '1px solid var(--tawn-line)', borderRadius: 'var(--r)', padding: '14px 18px' }}>
            <h2 style={{ fontSize: 'var(--sz-sm)', fontWeight: 600, marginBottom: 8 }}>log</h2>
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {log.map((line, i) => (
                <li key={i} style={{ fontSize: 'var(--sz-sm)', fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-2)' }}>
                  {line}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </Layout>
  )
}
