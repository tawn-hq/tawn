import { TextareaHTMLAttributes } from 'react'

export function Textarea({ style, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      style={{
        border: '1px solid var(--tawn-line)',
        borderRadius: 'var(--tawn-radius-sm)',
        padding: '8px 12px',
        background: 'var(--tawn-raised)',
        color: 'var(--tawn-text)',
        fontSize: 14,
        fontFamily: 'var(--tawn-font-body)',
        outline: 'none',
        width: '100%',
        resize: 'vertical',
        display: 'block',
        lineHeight: 1.5,
        ...style,
      }}
    />
  )
}
