import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Layout from '../components/Layout'
import { getDomains, getStatus, type DomainRow, type Status } from '../lib/api'

function Card({
  to,
  title,
  sub,
}: {
  to: string
  title: string
  sub: string
}) {
  return (
    <Link
      to={to}
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--r)',
        padding: '14px 18px',
        display: 'block',
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={(e) =>
        ((e.currentTarget as HTMLElement).style.borderColor = 'var(--lapis)')
      }
      onMouseLeave={(e) =>
        ((e.currentTarget as HTMLElement).style.borderColor = 'var(--border)')
      }
    >
      <div style={{ fontWeight: 600, color: 'var(--lapis)' }}>{title}</div>
      <div style={{ fontSize: 'var(--sz-sm)', color: 'var(--text-muted)', marginTop: 2 }}>
        {sub}
      </div>
    </Link>
  )
}

export default function Home() {
  const [status, setStatus] = useState<Status | null>(null)
  const [domains, setDomains] = useState<DomainRow[]>([])

  useEffect(() => {
    getStatus().then(setStatus).catch(() => {})
    getDomains().then((rows) => setDomains(rows.filter((d) => d.nav))).catch(() => {})
  }, [])

  return (
    <Layout>
      <h1
        style={{
          fontSize: 'var(--sz-xl)',
          fontWeight: 800,
          letterSpacing: '-0.03em',
          marginBottom: 6,
        }}
      >
        taw<span style={{ color: 'var(--tawn-lapis)' }}>n</span>
      </h1>
      <p style={{ color: 'var(--tawn-text-2)', marginBottom: 32, fontSize: 'var(--sz-sm)' }}>
        the twin you own · 127.0.0.1 only
        {status && ` · ${status.initialized ? 'ready' : 'run tawn init first'}`}
      </p>

      <section style={{ marginBottom: 32 }}>
        <h2
          style={{
            fontSize: 'var(--sz-sm)',
            fontWeight: 600,
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            marginBottom: 12,
          }}
        >
          quick actions
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
          <Card to="/chat" title="chat" sub="talk to your twin" />
          <Card to="/grants" title="grants" sub="manage access controls" />
          <Card to="/domain/create" title="+ domain" sub="track something new" />
          <Card to="/setup" title="setup" sub="configure providers & models" />
        </div>
      </section>

      {domains.length > 0 && (
        <section>
          <h2
            style={{
              fontSize: 'var(--sz-sm)',
              fontWeight: 600,
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              marginBottom: 12,
            }}
          >
            enabled domains
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
            {domains.map((d) => (
              <Card
                key={d.name}
                to={`/domain/${d.name}`}
                title={d.label}
                sub={`${d.name} domain`}
              />
            ))}
          </div>
        </section>
      )}

      {domains.length === 0 && (
        <p style={{ color: 'var(--text-muted)', fontSize: 'var(--sz-sm)' }}>
          No domains enabled yet.{' '}
          <Link to="/domain/create">Create one</Link> or{' '}
          <Link to="/setup">run setup</Link>.
        </p>
      )}
    </Layout>
  )
}
