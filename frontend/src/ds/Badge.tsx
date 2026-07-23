import { ReactNode } from 'react'

type Domain = 'work' | 'wealth' | 'research' | 'academic' | 'hobby'
type Status = 'good' | 'warn' | 'crit' | 'info'

interface BadgeProps {
  children: ReactNode
  domain?: Domain
  status?: Status
  tone?: 'neutral' | 'lapis'
}

const DOMAIN_COLOR: Record<Domain, string> = {
  work: 'var(--tawn-work)',
  wealth: 'var(--tawn-wealth)',
  research: 'var(--tawn-research)',
  academic: 'var(--tawn-academic)',
  hobby: 'var(--tawn-text-2)',
}

const STATUS_COLOR: Record<Status, string> = {
  good: 'var(--tawn-good)',
  warn: 'var(--tawn-warn)',
  crit: 'var(--tawn-crit)',
  info: 'var(--tawn-info)',
}

export function Badge({ children, domain, status, tone = 'neutral' }: BadgeProps) {
  let color = 'var(--tawn-text-2)'
  if (domain && DOMAIN_COLOR[domain]) color = DOMAIN_COLOR[domain]
  else if (status && STATUS_COLOR[status]) color = STATUS_COLOR[status]
  else if (tone === 'lapis') color = 'var(--tawn-lapis)'

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 600, color, background: 'var(--tawn-surface)', border: '1px solid var(--tawn-line)', borderRadius: 999, padding: '3px 9px', fontFamily: 'var(--tawn-font-mono)' }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0 }} />
      {children}
    </span>
  )
}
