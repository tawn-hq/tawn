import { useState, ReactNode, CSSProperties } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps {
  children: ReactNode
  variant?: Variant
  size?: Size
  disabled?: boolean
  onClick?: (e: React.MouseEvent) => void
  type?: 'button' | 'submit' | 'reset'
  style?: CSSProperties
}

const sizes: Record<Size, CSSProperties> = {
  sm: { padding: '6px 12px', fontSize: 12 },
  md: { padding: '8px 18px', fontSize: 13 },
  lg: { padding: '10px 22px', fontSize: 14, borderRadius: 'var(--tawn-radius)' },
}

const variants: Record<Variant, CSSProperties> = {
  primary: { background: 'var(--tawn-lapis)', color: '#fff' },
  secondary: { background: 'var(--tawn-raised)', color: 'var(--tawn-text)', border: '1px solid var(--tawn-line)' },
  ghost: { background: 'transparent', color: 'var(--tawn-text-2)' },
  danger: { background: 'var(--tawn-crit)', color: '#fff' },
}

const hoverBg: Record<Variant, string> = {
  primary: 'var(--tawn-lapis-deep)',
  secondary: 'var(--tawn-line)',
  ghost: 'var(--tawn-raised)',
  danger: '#a53535',
}

export function Button({ children, variant = 'primary', size = 'md', disabled, onClick, type = 'button', style }: ButtonProps) {
  const [hover, setHover] = useState(false)
  const v = variants[variant]
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        fontFamily: 'var(--tawn-font-body)',
        fontWeight: 600,
        fontSize: 13,
        border: 'none',
        borderRadius: 'var(--tawn-radius-sm)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        transition: 'background 0.15s, opacity 0.15s',
        ...v,
        ...sizes[size],
        background: hover && !disabled ? hoverBg[variant] : (v.background as string),
        opacity: disabled ? 0.5 : 1,
        ...style,
      }}
    >
      {children}
    </button>
  )
}
