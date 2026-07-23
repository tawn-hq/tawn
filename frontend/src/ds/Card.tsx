import { ReactNode, CSSProperties, MouseEvent } from 'react'

interface CardProps {
  children: ReactNode
  style?: CSSProperties
  padded?: boolean
  onClick?: (e: MouseEvent<HTMLDivElement>) => void
}

export function Card({ children, style, padded = true, onClick }: CardProps) {
  return (
    <div onClick={onClick} style={{ border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', background: 'var(--tawn-surface)', padding: padded ? '16px 20px' : 0, ...style }}>
      {children}
    </div>
  )
}
