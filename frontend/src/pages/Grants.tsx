import { FormEvent, useEffect, useState } from 'react'
import Layout from '../components/Layout'
import { getGrants, putGrants, type Grants } from '../lib/api'

function PathList({
  label,
  paths,
  onChange,
}: {
  label: string
  paths: string[]
  onChange: (v: string[]) => void
}) {
  const [draft, setDraft] = useState('')

  function add() {
    const p = draft.trim()
    if (p && !paths.includes(p)) {
      onChange([...paths, p])
    }
    setDraft('')
  }

  return (
    <div style={{ marginBottom: 20 }}>
      <label
        style={{
          display: 'block',
          fontSize: 'var(--sz-sm)',
          fontWeight: 600,
          color: 'var(--text-muted)',
          marginBottom: 6,
        }}
      >
        {label}
      </label>
      <ul style={{ listStyle: 'none', marginBottom: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {paths.map((p) => (
          <li key={p} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <code style={{ flex: 1, fontSize: 'var(--sz-sm)' }}>{p}</code>
            <button
              onClick={() => onChange(paths.filter((x) => x !== p))}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--error)',
                cursor: 'pointer',
                fontSize: 'var(--sz-sm)',
              }}
            >
              remove
            </button>
          </li>
        ))}
        {paths.length === 0 && (
          <li style={{ fontSize: 'var(--sz-sm)', color: 'var(--text-muted)' }}>none</li>
        )}
      </ul>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), add())}
          placeholder="/path/to/add"
          style={{
            flex: 1,
            border: '1px solid var(--border)',
            borderRadius: 'var(--r-sm)',
            padding: '5px 10px',
            background: 'var(--bg-raised)',
            color: 'var(--text)',
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--sz-sm)',
          }}
        />
        <button
          onClick={add}
          disabled={!draft.trim()}
          style={{
            padding: '5px 12px',
            background: 'var(--bg-raised)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--r-sm)',
            cursor: draft.trim() ? 'pointer' : 'not-allowed',
            opacity: draft.trim() ? 1 : 0.5,
            fontSize: 'var(--sz-sm)',
          }}
        >
          add
        </button>
      </div>
    </div>
  )
}

export default function GrantsPage() {
  const [grants, setGrants] = useState<Grants | null>(null)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getGrants().then(setGrants).catch((e: Error) => setError(e.message))
  }, [])

  async function save(e: FormEvent) {
    e.preventDefault()
    if (!grants) return
    setError(null)
    try {
      await putGrants(grants)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'save failed')
    }
  }

  if (error && !grants) {
    return (
      <Layout narrow>
        <p style={{ color: 'var(--error)' }}>{error}</p>
      </Layout>
    )
  }
  if (!grants) {
    return (
      <Layout narrow>
        <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
      </Layout>
    )
  }

  return (
    <Layout narrow>
      <h1 style={{ fontSize: 'var(--sz-xl)', fontWeight: 700, marginBottom: 8 }}>grants</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: 28, fontSize: 'var(--sz-sm)' }}>
        Deny-all by default. Every access is logged to the audit trail.
      </p>

      <form onSubmit={save}>
        <PathList
          label="Read paths"
          paths={grants.read}
          onChange={(v) => setGrants({ ...grants, read: v })}
        />
        <PathList
          label="Write paths"
          paths={grants.write}
          onChange={(v) => setGrants({ ...grants, write: v })}
        />

        <div style={{ marginBottom: 20 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={grants.system}
              onChange={(e) => setGrants({ ...grants, system: e.target.checked })}
            />
            <span style={{ fontSize: 'var(--sz-sm)' }}>
              <strong>system awareness</strong> — full-system context (per-session opt-in)
            </span>
          </label>
        </div>

        {error && (
          <p style={{ color: 'var(--error)', fontSize: 'var(--sz-sm)', marginBottom: 12 }}>
            {error}
          </p>
        )}

        <button
          type="submit"
          style={{
            padding: '8px 20px',
            background: 'var(--lapis)',
            color: '#fff',
            border: 'none',
            borderRadius: 'var(--r)',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          {saved ? '✓ saved' : 'save grants'}
        </button>
      </form>
    </Layout>
  )
}
