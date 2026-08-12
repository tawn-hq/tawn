import { ChangeEvent } from 'react'

interface CheckboxProps {
  label: string
  checked?: boolean
  onChange?: (e: ChangeEvent<HTMLInputElement>) => void
  hint?: string
  disabled?: boolean
}

export function Checkbox({ label, checked, onChange, hint, disabled }: CheckboxProps) {
  return (
    <label
      style={{
        display: 'flex', alignItems: 'center', gap: 8, fontSize: 13,
        cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.55 : 1,
      }}
    >
      <input
        type="checkbox" checked={checked} onChange={onChange} disabled={disabled}
        style={{ accentColor: 'var(--tawn-lapis)' }}
      />
      <span style={{ color: 'var(--tawn-text)' }}>
        {label}
        {hint && <span style={{ color: 'var(--tawn-text-2)' }}> — {hint}</span>}
      </span>
    </label>
  )
}
