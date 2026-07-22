import { InputHTMLAttributes } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  mono?: boolean
}

export function Input({ mono, style, ...props }: InputProps) {
  return (
    <input
      {...props}
      style={{
        border: '1px solid var(--tawn-line)',
        borderRadius: 'var(--tawn-radius-sm)',
        padding: '8px 12px',
        background: 'var(--tawn-raised)',
        color: 'var(--tawn-text)',
        fontSize: 14,
        fontFamily: mono ? 'var(--tawn-font-mono)' : 'var(--tawn-font-body)',
        outline: 'none',
        width: '100%',
        display: 'block',
        ...style,
      }}
    />
  )
}
