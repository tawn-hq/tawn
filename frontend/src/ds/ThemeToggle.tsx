import { useEffect, useState } from 'react'
import { getThemePref, setThemePref, applyThemePref, type ThemePref } from '../lib/theme'

const ORDER: ThemePref[] = ['system', 'light', 'dark']
const LABEL: Record<ThemePref, string> = { system: 'system', light: 'light', dark: 'dark' }

function Icon({ pref }: { pref: ThemePref }) {
  const stroke = 'currentColor'
  const common = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke, strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  if (pref === 'light') {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
      </svg>
    )
  }
  if (pref === 'dark') {
    return (
      <svg {...common}>
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    )
  }
  return (
    <svg {...common}>
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </svg>
  )
}

/** Cycles system → light → dark → system. Applied on mount (index.html's
 * inline script only covers explicit light/dark before paint; a 'system'
 * preference needs no attribute at all, which is already the default DOM
 * state, so there's nothing to re-apply there — this call is a no-op in
 * that case and only matters after localStorage had 'light'/'dark' saved
 * from a previous visit). */
export function ThemeToggle() {
  const [pref, setPref] = useState<ThemePref>(() => getThemePref())

  useEffect(() => { applyThemePref(pref) }, [])

  function cycle() {
    const next = ORDER[(ORDER.indexOf(pref) + 1) % ORDER.length]
    setPref(next)
    setThemePref(next)
  }

  return (
    <button
      onClick={cycle}
      title={`theme: ${LABEL[pref]} (click to change)`}
      aria-label={`theme: ${LABEL[pref]}`}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 30, height: 30, flexShrink: 0,
        border: '1px solid var(--tawn-line)', borderRadius: 8,
        background: 'var(--tawn-surface)', color: 'var(--tawn-text-2)',
        cursor: 'pointer',
      }}
    >
      <Icon pref={pref} />
    </button>
  )
}
