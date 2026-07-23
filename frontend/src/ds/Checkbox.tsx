import { ChangeEvent } from 'react'

interface CheckboxProps {
  label: string
  checked?: boolean
  onChange?: (e: ChangeEvent<HTMLInputElement>) => void
  hint?: string
}

export function Checkbox({ label, checked, onChange, hint }: CheckboxProps) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
      <input type="checkbox" checked={checked} onChange={onChange} style={{ accentColor: 'var(--tawn-lapis)' }} />
      <span style={{ color: 'var(--tawn-text)' }}>
        {label}
        {hint && <span style={{ color: 'var(--tawn-text-2)' }}> — {hint}</span>}
      </span>
    </label>
  )
}
