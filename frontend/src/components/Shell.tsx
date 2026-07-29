import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Logo, ThemeToggle } from '../ds'

/**
 * The application frame: a grouped sidebar, a slim header, and a content well.
 *
 * Nine destinations in one flat row gave every page equal weight and no shape —
 * "activity" sat beside "chat" as though they were the same kind of thing. The
 * groups below say what each destination is *for*, so the nav teaches the
 * product rather than just listing it.
 */

interface NavItem {
  label: string
  to: string
  hint: string
}

interface NavGroup {
  title: string
  items: NavItem[]
}

export const NAV: NavGroup[] = [
  {
    title: 'your twin',
    items: [
      { label: 'dashboard', to: '/dashboard', hint: 'today at a glance' },
      { label: 'chat', to: '/chat', hint: 'ask, with your memory in context' },
    ],
  },
  {
    title: 'knowledge',
    items: [
      { label: 'memory', to: '/memory', hint: 'everything it has read' },
      { label: 'notes', to: '/notes', hint: 'what you told it directly' },
      { label: 'wiki', to: '/wiki', hint: 'what it worked out' },
    ],
  },
  {
    title: 'capability',
    items: [
      { label: 'tools', to: '/tools', hint: 'servers, skills, generated tools' },
      { label: 'agents', to: '/agents', hint: 'the tools that feed it' },
    ],
  },
  {
    title: 'system',
    items: [
      { label: 'activity', to: '/observability', hint: 'what it did, and the cost' },
      { label: 'settings', to: '/settings', hint: 'grants, models, database' },
    ],
  },
]

const SIDEBAR_WIDTH = 208
const HEADER_HEIGHT = 56
const COLLAPSE_KEY = 'tawn_sidebar_collapsed'

function useIsMobile() {
  const [mobile, setMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < 900,
  )
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 899px)')
    const handler = (e: MediaQueryListEvent) => setMobile(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return mobile
}

function StatusPill() {
  const [label, setLabel] = useState('local')
  const [publicUrl, setPublicUrl] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/setup/host')
      .then((r) => r.json())
      .then((d: { ok: boolean }) => { if (d.ok) setLabel('tawn:8787') })
      .catch(() => {})
    fetch('/api/setup/tunnel')
      .then((r) => r.json())
      .then((d: { active: boolean; url: string | null }) => {
        if (d.active && d.url) setPublicUrl(d.url)
      })
      .catch(() => {})
  }, [])

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-2)', border: '1px solid var(--tawn-line)', borderRadius: 999, padding: '4px 10px 4px 8px' }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: publicUrl ? 'var(--tawn-warn)' : 'var(--tawn-good)', flexShrink: 0 }} />
      {publicUrl ? (
        <a href={publicUrl} target="_blank" rel="noreferrer" style={{ color: 'var(--tawn-lapis)', textDecoration: 'none' }} title={`reachable from the internet: ${publicUrl}`}>
          {label} · public ↗
        </a>
      ) : label}
    </span>
  )
}

function NavRow({ item, collapsed, onGo }: { item: NavItem; collapsed: boolean; onGo: () => void }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [hover, setHover] = useState(false)
  const active =
    location.pathname === item.to ||
    (item.to !== '/' && location.pathname.startsWith(item.to))

  return (
    <a
      href={item.to}
      title={collapsed ? `${item.label} — ${item.hint}` : item.hint}
      onClick={(e) => { e.preventDefault(); navigate(item.to); onGo() }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 9,
        padding: collapsed ? '8px 0' : '7px 10px',
        justifyContent: collapsed ? 'center' : 'flex-start',
        margin: '1px 0',
        borderRadius: 'var(--tawn-radius-sm)',
        fontSize: 13.5,
        textDecoration: 'none',
        color: active ? 'var(--tawn-lapis)' : hover ? 'var(--tawn-text)' : 'var(--tawn-text-2)',
        fontWeight: active ? 600 : 500,
        background: active ? 'var(--tawn-lapis-soft)' : hover ? 'var(--tawn-raised)' : 'transparent',
        transition: 'background 0.14s, color 0.14s',
      }}
    >
      {/* A rail rather than an icon: it marks position without inventing a
          glyph for abstractions like "activity" that no icon says well. */}
      <span
        style={{
          width: 2, height: 15, borderRadius: 1, flexShrink: 0,
          background: active ? 'var(--tawn-lapis)' : 'transparent',
        }}
      />
      {collapsed ? item.label.slice(0, 2) : item.label}
    </a>
  )
}

function Sidebar({ collapsed, onGo }: { collapsed: boolean; onGo: () => void }) {
  return (
    <nav style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '14px 10px 24px' }}>
      {NAV.map((group) => (
        <div key={group.title}>
          {!collapsed && (
            <div style={{ fontSize: 10, fontFamily: 'var(--tawn-font-mono)', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--tawn-text-3)', padding: '0 12px 5px' }}>
              {group.title}
            </div>
          )}
          {group.items.map((item) => (
            <NavRow key={item.to} item={item} collapsed={collapsed} onGo={onGo} />
          ))}
        </div>
      ))}
    </nav>
  )
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()
  const mobile = useIsMobile()
  const [drawer, setDrawer] = useState(false)
  const [collapsed, setCollapsed] = useState(
    () => typeof window !== 'undefined' && localStorage.getItem(COLLAPSE_KEY) === '1',
  )

  function toggleCollapse() {
    setCollapsed((c) => {
      localStorage.setItem(COLLAPSE_KEY, c ? '0' : '1')
      return !c
    })
  }

  const railWidth = collapsed ? 62 : SIDEBAR_WIDTH

  return (
    <div style={{ background: 'var(--tawn-bg)', minHeight: '100vh' }}>
      <header style={{ position: 'sticky', top: 0, zIndex: 20, height: HEADER_HEIGHT, borderBottom: '1px solid var(--tawn-line)', background: 'var(--tawn-bg)', display: 'flex', alignItems: 'center', gap: 10, padding: mobile ? '0 14px' : '0 18px' }}>
        {mobile && (
          <button
            onClick={() => setDrawer(!drawer)}
            aria-label="menu"
            style={{ width: 34, height: 34, flexShrink: 0, border: '1px solid var(--tawn-line)', borderRadius: 8, background: 'var(--tawn-surface)', cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4 }}
          >
            {[0, 1, 2].map((i) => (
              <span key={i} style={{ width: 16, height: 2, background: 'var(--tawn-text)', borderRadius: 1 }} />
            ))}
          </button>
        )}
        <div
          style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', width: mobile ? undefined : railWidth - 18, transition: 'width 0.16s ease' }}
          onClick={() => navigate('/dashboard')}
        >
          <Logo size={mobile ? 20 : 22} />
        </div>
        {!mobile && (
          <button
            onClick={toggleCollapse}
            aria-label={collapsed ? 'expand sidebar' : 'collapse sidebar'}
            title={collapsed ? 'expand sidebar' : 'collapse sidebar'}
            style={{ width: 26, height: 26, border: '1px solid var(--tawn-line)', borderRadius: 7, background: 'var(--tawn-surface)', color: 'var(--tawn-text-2)', cursor: 'pointer', fontSize: 12, lineHeight: 1 }}
          >
            {collapsed ? '›' : '‹'}
          </button>
        )}
        <span style={{ flex: 1 }} />
        {!mobile && <StatusPill />}
        <ThemeToggle />
      </header>

      <div style={{ display: 'flex', alignItems: 'flex-start' }}>
        {!mobile && (
          <aside style={{ width: railWidth, flexShrink: 0, position: 'sticky', top: HEADER_HEIGHT, height: `calc(100vh - ${HEADER_HEIGHT}px)`, overflowY: 'auto', borderRight: '1px solid var(--tawn-line)', transition: 'width 0.16s ease' }}>
            <Sidebar collapsed={collapsed} onGo={() => {}} />
          </aside>
        )}

        {mobile && drawer && (
          <>
            <div onClick={() => setDrawer(false)} style={{ position: 'fixed', inset: 0, top: HEADER_HEIGHT, background: 'rgba(0,0,0,0.45)', zIndex: 25 }} />
            <aside style={{ position: 'fixed', top: HEADER_HEIGHT, bottom: 0, left: 0, width: 'min(260px, 82vw)', background: 'var(--tawn-bg)', borderRight: '1px solid var(--tawn-line)', zIndex: 26, overflowY: 'auto' }}>
              <Sidebar collapsed={false} onGo={() => setDrawer(false)} />
            </aside>
          </>
        )}

        <main style={{ flex: 1, minWidth: 0 }}>{children}</main>
      </div>
    </div>
  )
}

/**
 * One page heading, used by every page, so titles sit in the same place at the
 * same size no matter where you navigate.
 */
export function Page({
  title,
  subtitle,
  actions,
  width = 940,
  children,
}: {
  title?: string
  subtitle?: string
  actions?: React.ReactNode
  width?: number
  children: React.ReactNode
}) {
  return (
    <div style={{ maxWidth: width, margin: '0 auto', padding: '28px 24px 64px' }}>
      {title && (
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: subtitle ? 18 : 20, flexWrap: 'wrap' }}>
          <div style={{ minWidth: 0 }}>
            <h1 style={{ fontSize: 21, fontWeight: 700, marginBottom: subtitle ? 3 : 0 }}>{title}</h1>
            {subtitle && (
              <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', margin: 0 }}>{subtitle}</p>
            )}
          </div>
          {actions && <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>{actions}</div>}
        </div>
      )}
      {children}
    </div>
  )
}
