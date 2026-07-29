import { useEffect, useState } from 'react'
import { getProfile, putProfile } from '../lib/api'
import { useErrors } from '../components/Errors'

interface Profile {
  name?: string
  role?: string
  focus?: string
  [key: string]: string | undefined
}

export default function Profile() {
  const { report } = useErrors()
  const reportError = (e: unknown) => report(e instanceof Error ? e.message : String(e))
  const [profile, setProfile] = useState<Profile>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getProfile().then(setProfile).catch(reportError)
  }, [])

  function set(k: string, v: string) {
    setProfile((p) => ({ ...p, [k]: v }))
    setSaved(false)
  }

  async function save(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await putProfile({
        name: profile.name ?? '',
        role: profile.role ?? '',
        focus: profile.focus ?? '',
        extra: Object.fromEntries(
          Object.entries(profile).filter(([k]) => !['name', 'role', 'focus'].includes(k) && k !== undefined)
        ) as Record<string, string>,
      })
      setSaved(true)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main style={{ maxWidth: 600, margin: '40px auto', padding: '0 20px' }}>
      <h1 style={{ fontFamily: 'var(--tawn-font-display)', fontSize: 28, marginBottom: 8 }}>
        your profile
      </h1>
      <p style={{ color: 'var(--tawn-text-2)', fontSize: 13, marginBottom: 32 }}>
        injected into every Tawn conversation so your twin knows who it's talking to.
        stored only at <code>~/.tawn/personality/profile.yaml</code>.
      </p>

      <form onSubmit={save} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {[
          { key: 'name', label: 'name', placeholder: 'your name' },
          { key: 'role', label: 'role', placeholder: 'what you do — one line' },
          { key: 'focus', label: 'current focus', placeholder: 'what you mainly use Tawn for right now' },
        ].map(({ key, label, placeholder }) => (
          <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ fontSize: 12, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              {label}
            </label>
            <input
              value={profile[key] ?? ''}
              onChange={(e) => set(key, e.target.value)}
              placeholder={placeholder}
              style={{
                background: 'var(--tawn-surface)',
                border: '1px solid var(--tawn-line)',
                borderRadius: 6,
                padding: '10px 12px',
                color: 'var(--tawn-text)',
                fontSize: 14,
                outline: 'none',
              }}
            />
          </div>
        ))}

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
          <button
            type="submit"
            disabled={saving}
            style={{
              background: 'var(--tawn-lapis)',
              color: '#fff',
              border: 'none',
              borderRadius: 6,
              padding: '10px 24px',
              fontSize: 14,
              fontWeight: 600,
              cursor: saving ? 'wait' : 'pointer',
            }}
          >
            {saving ? 'saving…' : 'save profile'}
          </button>
          {saved && <span style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>saved ✓</span>}
          {error && <span style={{ fontSize: 13, color: '#e55' }}>{error}</span>}
        </div>
      </form>

      <div style={{ marginTop: 48, borderTop: '1px solid var(--tawn-line)', paddingTop: 24 }}>
        <p style={{ fontSize: 12, color: 'var(--tawn-text-2)' }}>
          this profile is also settable via CLI: <code>tawn chat</code> → first run asks these questions,
          or use <code>/profile</code> inside chat to edit.
        </p>
      </div>
    </main>
  )
}
