import { SelectHTMLAttributes, ReactNode } from 'react'

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  children: ReactNode
}

export function Select({ children, style, ...props }: SelectProps) {
  return (
    <select
      {...props}
      style={{
        border: '1px solid var(--tawn-line)',
        borderRadius: 'var(--tawn-radius-sm)',
        padding: '7px 10px',
        background: 'var(--tawn-raised)',
        color: 'var(--tawn-text)',
        fontSize: 13,
        fontFamily: 'var(--tawn-font-body)',
        outline: 'none',
        ...style,
      }}
    >
      {children}
    </select>
  )
}
