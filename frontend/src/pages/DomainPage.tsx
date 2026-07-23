import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import Layout from '../components/Layout'

interface Stat {
  label: string
  value: string
  sublabel?: string
}

interface TableSection {
  type: 'table'
  columns: string[]
  rows: string[][]
}

interface ListSection {
  type: 'list'
  items: { label: string; value?: string }[]
}

interface EmptySection {
  type: 'empty'
  message: string
}

type Section = TableSection | ListSection | EmptySection

interface DomainView {
  title: string
  stat?: Stat
  sections: Section[]
}

function StatCard({ stat }: { stat: Stat }) {
  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--r)',
        padding: '16px 20px',
        marginBottom: 24,
        display: 'inline-block',
      }}
    >
      <div style={{ fontSize: 'var(--sz-sm)', color: 'var(--text-muted)' }}>{stat.label}</div>
      <div style={{ fontSize: 32, fontWeight: 800, letterSpacing: '-0.03em' }}>{stat.value}</div>
      {stat.sublabel && (
        <div style={{ fontSize: 'var(--sz-sm)', color: 'var(--text-muted)' }}>{stat.sublabel}</div>
      )}
    </div>
  )
}

function SectionView({ section }: { section: Section }) {
  if (section.type === 'empty') {
    return (
      <p style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>{section.message}</p>
    )
  }
  if (section.type === 'list') {
    return (
      <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {section.items.map((item, i) => (
          <li key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
            <span>{item.label}</span>
            {item.value && <span style={{ color: 'var(--text-muted)' }}>{item.value}</span>}
          </li>
        ))}
      </ul>
    )
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--sz-sm)' }}>
        <thead>
          <tr>
            {section.columns.map((col) => (
              <th
                key={col}
                style={{
                  textAlign: 'left',
                  padding: '6px 10px',
                  borderBottom: '1px solid var(--border)',
                  color: 'var(--text-muted)',
                  fontWeight: 600,
                }}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {section.rows.map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td
                  key={ci}
                  style={{ padding: '6px 10px', borderBottom: '1px solid var(--border)' }}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function DomainPage() {
  const { name } = useParams<{ name: string }>()
  const [view, setView] = useState<DomainView | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!name) return
    fetch(`/api/${name}/view`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      })
      .then(setView)
      .catch((e: Error) => setError(e.message))
  }, [name])

  if (error) {
    return (
      <Layout narrow>
        <p style={{ color: 'var(--error)' }}>Failed to load domain: {error}</p>
      </Layout>
    )
  }
  if (!view) {
    return (
      <Layout narrow>
        <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
      </Layout>
    )
  }

  return (
    <Layout>
      <h1 style={{ fontSize: 'var(--sz-xl)', fontWeight: 700, marginBottom: 20 }}>
        {view.title}
      </h1>
      {view.stat && <StatCard stat={view.stat} />}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
        {view.sections.map((s, i) => (
          <SectionView key={i} section={s} />
        ))}
      </div>
    </Layout>
  )
}
