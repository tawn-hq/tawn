/** Theme preference: 'system' follows prefers-color-scheme (no attribute
 * set — the CSS media query handles it); 'light'/'dark' pin an explicit
 * choice via the data-theme attribute. Persisted to localStorage so the
 * pick survives reloads; index.html applies it pre-paint to avoid a flash. */

export type ThemePref = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'tawn-theme'

export function getThemePref(): ThemePref {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch { /* localStorage unavailable (private mode, etc.) */ }
  return 'system'
}

export function setThemePref(pref: ThemePref): void {
  try {
    if (pref === 'system') localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, pref)
  } catch { /* ignore */ }
  applyThemePref(pref)
}

export function applyThemePref(pref: ThemePref): void {
  if (pref === 'system') document.documentElement.removeAttribute('data-theme')
  else document.documentElement.setAttribute('data-theme', pref)
}
