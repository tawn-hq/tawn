interface StatCardProps {
  label: string
  value: string | number
  sublabel?: string
}

export function StatCard({ label, value, sublabel }: StatCardProps) {
  return (
    <div style={{ border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', padding: '16px 20px', background: 'var(--tawn-surface)' }}>
      <div style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>{label}</div>
      <div style={{ fontSize: 32, fontWeight: 800, letterSpacing: '-0.03em', fontFamily: 'var(--tawn-font-display)', color: 'var(--tawn-text)' }}>{value}</div>
      {sublabel && <div style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>{sublabel}</div>}
    </div>
  )
}
