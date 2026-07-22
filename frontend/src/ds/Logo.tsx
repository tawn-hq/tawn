interface LogoProps {
  size?: number
  withWordmark?: boolean
}

export function Logo({ size = 24, withWordmark = true }: LogoProps) {
  const mark = (
    <svg width={size} height={size} viewBox="0 0 256 256" aria-label="tawn">
      <ellipse cx={128} cy={192} rx={62} ry={24} fill="var(--tawn-text)" />
      <ellipse cx={128} cy={148} rx={45} ry={21} fill="var(--tawn-text)" />
      <ellipse cx={128} cy={108} rx={27} ry={17} fill="var(--tawn-lapis)" />
    </svg>
  )
  if (!withWordmark) return mark
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      {mark}
      <span style={{ fontWeight: 700, fontSize: size * 0.75, letterSpacing: '-0.02em', fontFamily: 'var(--tawn-font-display)', color: 'var(--tawn-text)' }}>
        taw<span style={{ color: 'var(--tawn-lapis)' }}>n</span>
      </span>
    </span>
  )
}
