import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Logo } from './Logo'

function useIsMobile() {
  const [mobile, setMobile] = useState(() => typeof window !== 'undefined' && window.innerWidth < 640)
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 639px)')
    const handler = (e: MediaQueryListEvent) => setMobile(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return mobile
}

export interface NavLink {
  label: string
  to: string
}

function StatusPill() {
  const [label, setLabel] = useState('local')
  const [hasPublic, setHasPublic] = useState(false)
  const [publicUrl, setPublicUrl] = useState<string | null>(null)

  useEffect(() => {
    // check hostname then tunnel — both are fire-and-forget, no spinner needed
    fetch('/api/setup/host').then((r) => r.json()).then((d: { ok: boolean }) => {
      if (d.ok) setLabel('tawn:8787')
    }).catch(() => {})
    fetch('/api/setup/tunnel').then((r) => r.json()).then((d: { active: boolean; url: string | null }) => {
      if (d.active && d.url) { setHasPublic(true); setPublicUrl(d.url) }
    }).catch(() => {})
  }, [])

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-2)', border: '1px solid var(--tawn-line)', borderRadius: 999, padding: '4px 10px 4px 8px' }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--tawn-good)', flexShrink: 0 }} />
      {hasPublic && publicUrl ? (
        <a href={publicUrl} target="_blank" rel="noreferrer" style={{ color: 'var(--tawn-lapis)', textDecoration: 'none' }} title={`public: ${publicUrl}`}>
          {label} · public ↗
        </a>
      ) : label}
    </span>
  )
}

function MenuToggle({ open, onClick }: { open: boolean; onClick: () => void }) {
  const bar: React.CSSProperties = { width: 18, height: 2, background: 'var(--tawn-text)', borderRadius: 1, transition: 'transform 0.15s, opacity 0.15s' }
  return (
    <button onClick={onClick} aria-label="menu" style={{ width: 34, height: 34, flexShrink: 0, border: '1px solid var(--tawn-line)', borderRadius: 8, background: 'var(--tawn-surface)', cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
      <span style={{ ...bar, transform: open ? 'translateY(6px) rotate(45deg)' : 'none' }} />
      <span style={{ ...bar, opacity: open ? 0 : 1 }} />
      <span style={{ ...bar, transform: open ? 'translateY(-6px) rotate(-45deg)' : 'none' }} />
    </button>
  )
}

interface NavBarProps {
  links?: NavLink[]
  showStatus?: boolean
  right?: React.ReactNode
}

export function NavBar({ links = [], showStatus = false, right }: NavBarProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const mobile = useIsMobile()

  function NavItem({ l }: { l: NavLink }) {
    const [hover, setHover] = useState(false)
    const isActive = location.pathname === l.to || (l.to !== '/' && location.pathname.startsWith(l.to))
    return (
      <a
        href={l.to}
        onClick={(e) => { e.preventDefault(); navigate(l.to); setOpen(false) }}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        style={mobile ? {
          fontSize: 15, cursor: 'pointer', display: 'block', width: '100%',
          color: isActive ? 'var(--tawn-lapis)' : 'var(--tawn-text)',
          fontWeight: isActive ? 600 : 500,
          padding: '14px 20px',
          background: isActive ? 'var(--tawn-lapis-soft)' : 'transparent',
        } : {
          fontSize: 13, whiteSpace: 'nowrap', cursor: 'pointer',
          color: isActive ? 'var(--tawn-lapis)' : hover ? 'var(--tawn-text)' : 'var(--tawn-text-2)',
          fontWeight: isActive ? 600 : 500,
          padding: '7px 14px',
          borderRadius: 999,
          background: isActive ? 'var(--tawn-lapis-soft)' : hover ? 'var(--tawn-raised)' : 'transparent',
          transition: 'background 0.15s, color 0.15s',
        }}
      >
        {l.label}
      </a>
    )
  }

  return (
    <header style={{ borderBottom: '1px solid var(--tawn-line)', background: 'var(--tawn-bg)', position: 'sticky', top: 0, zIndex: 10 }}>
      <nav style={{ maxWidth: 1040, margin: '0 auto', padding: mobile ? '0 14px' : '0 20px', height: 56, display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ paddingRight: mobile ? 8 : 16, cursor: 'pointer' }} onClick={() => navigate('/dashboard')}>
          <Logo size={mobile ? 20 : 22} />
        </div>
        {!mobile && links.map((l) => <NavItem key={l.to} l={l} />)}
        <span style={{ flex: 1 }} />
        {showStatus && !mobile && <StatusPill />}
        {right}
        {mobile && links.length > 0 && <MenuToggle open={open} onClick={() => setOpen(!open)} />}
      </nav>
      {mobile && open && (
        <div style={{ borderTop: '1px solid var(--tawn-line)', background: 'var(--tawn-bg)', padding: '6px 0' }}>
          {links.map((l) => <NavItem key={l.to} l={l} />)}
        </div>
      )}
    </header>
  )
}
