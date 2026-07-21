import { useEffect, useState } from 'react'
import { getAllModels, ModelRow } from '../lib/api'

const LOCALITY_COLOR: Record<string, string> = {
  local: '#4c4',
  cloud: 'var(--tawn-lapis)',
}

export default function Models() {
  const [models, setModels] = useState<ModelRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    getAllModels()
      .then(setModels)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const local = models.filter((m) => m.locality === 'local')
  const cloud = models.filter((m) => m.locality !== 'local')

  return (
    <main style={{ maxWidth: 800, margin: '40px auto', padding: '0 20px' }}>
      <h1 style={{ fontFamily: 'var(--tawn-font-display)', fontSize: 28, marginBottom: 8 }}>
        models
      </h1>
      <p style={{ color: 'var(--tawn-text-2)', fontSize: 13, marginBottom: 32 }}>
        all models available to Tawn. local models run on your machine; cloud models require API keys.
      </p>

      {loading && <p style={{ color: 'var(--tawn-text-2)' }}>loading…</p>}
      {error && <p style={{ color: '#e55' }}>{error}</p>}

      {[
        { title: 'local models', items: local, hint: 'runs on your machine — private by default' },
        { title: 'cloud models', items: cloud, hint: 'requires API key · use --sensitive to block these' },
      ].map(({ title, items, hint }) => (
        items.length > 0 && (
          <section key={title} style={{ marginBottom: 40 }}>
            <div style={{ marginBottom: 12 }}>
              <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>{title}</h2>
              <p style={{ fontSize: 12, color: 'var(--tawn-text-2)', margin: '4px 0 0' }}>{hint}</p>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--tawn-line)', color: 'var(--tawn-text-2)' }}>
                  {['target', 'provider', 'model', 'where'].map((h) => (
                    <th key={h} style={{ padding: '6px 10px', textAlign: 'left', fontWeight: 500, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((m) => (
                  <tr key={m.target} style={{ borderBottom: '1px solid var(--tawn-line)' }}>
                    <td style={{ padding: '10px', fontFamily: 'var(--tawn-font-mono)', fontSize: 12 }}>{m.target}</td>
                    <td style={{ padding: '10px', color: 'var(--tawn-text-2)' }}>{m.provider}</td>
                    <td style={{ padding: '10px', fontFamily: 'var(--tawn-font-mono)', fontSize: 12 }}>{m.model}</td>
                    <td style={{ padding: '10px' }}>
                      <span style={{
                        fontSize: 11,
                        fontWeight: 600,
                        color: LOCALITY_COLOR[m.locality] ?? 'var(--tawn-text-2)',
                        background: 'var(--tawn-surface)',
                        borderRadius: 4,
                        padding: '2px 7px',
                      }}>
                        {m.locality}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )
      ))}

      {!loading && models.length === 0 && !error && (
        <p style={{ color: 'var(--tawn-text-2)' }}>
          no models configured. run <code>tawn setup</code> to get started.
        </p>
      )}
    </main>
  )
}
