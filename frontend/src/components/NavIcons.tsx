/** Inline monoline icons for the sidebar.
 *
 * Inline rather than an icon package: Tawn's web surface must work with no
 * network, and a font or CDN sprite is one more thing to fail offline. They use
 * `currentColor` so the active, hover and dim nav states need no icon-specific
 * styling, and a 1.6 stroke to match the brand's monoline lettering.
 *
 * The sidebar keeps its active rail as well. The rail marks *position*; the icon
 * says *what*. Collapsed, the icon replaces a two-letter truncation that could
 * not distinguish "agents" from "activity".
 */
import { ReactNode } from 'react'

const S = ({ children }: { children: ReactNode }) => (
  <svg
    width="15" height="15" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"
    aria-hidden="true" focusable="false" style={{ flexShrink: 0 }}
  >
    {children}
  </svg>
)

export const NAV_ICONS = {
  dashboard: <S><rect x="3" y="3" width="7" height="9" rx="1" /><rect x="14" y="3" width="7" height="5" rx="1" /><rect x="14" y="12" width="7" height="9" rx="1" /><rect x="3" y="16" width="7" height="5" rx="1" /></S>,
  chat: <S><path d="M21 12a8 8 0 0 1-8 8H8l-5 3 1.5-5A8 8 0 1 1 21 12Z" /></S>,
  memory: <S><ellipse cx="12" cy="5.5" rx="8" ry="3" /><path d="M4 5.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /><path d="M4 11.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></S>,
  notes: <S><path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H15l5 5v12a1 1 0 0 1-1 1H5.5A1.5 1.5 0 0 1 4 19.5Z" /><path d="M15 3v5h5" /><path d="M8 13h8M8 17h5" /></S>,
  wiki: <S><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5Z" /><path d="M8 7h8M8 11h6" /></S>,
  tools: <S><path d="M14.5 6.5a4 4 0 1 0 5 5L21 21l-2 0-6.5-9.5Z" /><path d="M9.5 3 3 9.5l3 3L12.5 6Z" /></S>,
  agents: <S><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="6" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M7.6 8 11 15.6M16.4 8 13 15.6M8.5 6h7" /></S>,
  observer: <S><path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z" /><circle cx="12" cy="12" r="2.6" /></S>,
  activity: <S><path d="M3 13h4l2.5-7 4 14L16 13h5" /></S>,
  settings: <S><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2.2" /><circle cx="10" cy="17" r="2.2" /></S>,
} as const

export type NavIconName = keyof typeof NAV_ICONS
