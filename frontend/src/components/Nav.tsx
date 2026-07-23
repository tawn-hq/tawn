import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import CairnMark from './CairnMark'

interface DomainRow {
  name: string
  label: string
  nav: boolean
}

const STATIC_LINKS = [
  { to: '/chat', label: 'chat' },
  { to: '/memory', label: 'memory' },
  { to: '/history', label: 'history' },
  { to: '/models', label: 'models' },
  { to: '/audit', label: 'audit' },
  { to: '/grants', label: 'grants' },
  { to: '/profile', label: 'profile' },
  { to: '/setup', label: 'setup' },
]

export default function Nav() {
  const [domains, setDomains] = useState<DomainRow[]>([])

  useEffect(() => {
    fetch('/api/domains')
      .then((r) => r.json())
      .then(setDomains)
      .catch(() => {})
  }, [])

  return (
    <header
      style={{
        borderBottom: '1px solid var(--tawn-line)',
        background: 'var(--tawn-bg)',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      <nav
        style={{
          maxWidth: 860,
          margin: '0 auto',
          padding: '0 20px',
          height: 48,
          display: 'flex',
          alignItems: 'center',
          gap: 20,
          overflowX: 'auto',
        }}
      >
        <NavLink to="/" style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <CairnMark size={24} />
          <span style={{ fontWeight: 700, letterSpacing: '-0.02em', fontFamily: 'var(--tawn-font-display)' }}>
            taw<span style={{ color: 'var(--tawn-lapis)' }}>n</span>
          </span>
        </NavLink>
        <span style={{ flex: 1 }} />
        {STATIC_LINKS.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            style={({ isActive }) => ({
              fontSize: 13,
              color: isActive ? 'var(--tawn-lapis)' : 'var(--tawn-text-2)',
              fontWeight: isActive ? 600 : 400,
              flexShrink: 0,
            })}
          >
            {label}
          </NavLink>
        ))}
        {domains.filter((d) => d.nav).map((d) => (
          <NavLink
            key={d.name}
            to={`/domain/${d.name}`}
            style={({ isActive }) => ({
              fontSize: 13,
              color: isActive ? 'var(--tawn-lapis)' : 'var(--tawn-text-2)',
              fontWeight: isActive ? 600 : 400,
              flexShrink: 0,
            })}
          >
            {d.label}
          </NavLink>
        ))}
        <NavLink
          to="/domain/create"
          style={{ fontSize: 13, color: 'var(--tawn-lapis)', fontWeight: 500, flexShrink: 0 }}
        >
          + domain
        </NavLink>
      </nav>
    </header>
  )
}
