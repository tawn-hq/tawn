import { useEffect, useRef } from 'react'
import { marked } from 'marked'
import { renderDiagramsIn } from '../lib/diagrams'

marked.setOptions({ breaks: true })

interface ChatBubbleProps {
  role: 'user' | 'assistant'
  children: string
  streaming?: boolean
  time?: string
}

export function ChatBubble({ role, children, streaming, time }: ChatBubbleProps) {
  const isUser = role === 'user'
  const contentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!contentRef.current) return
    if (isUser) {
      contentRef.current.textContent = children
      return
    }
    contentRef.current.innerHTML = marked.parse(children) as string
    // Skip diagram rendering while still streaming — a partial ```mermaid
    // fence re-parses (and fails) on every incoming token; wait for the
    // final, complete render instead of thrashing.
    if (!streaming) {
      renderDiagramsIn(contentRef.current)
    }
  }, [children, isUser, streaming])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', marginBottom: 16 }}>
      {!isUser && <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', marginBottom: 5, marginLeft: 3 }}>tawn</span>}
      <div style={{ maxWidth: '80%', padding: '11px 15px', borderRadius: isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px', background: isUser ? 'var(--tawn-lapis)' : 'var(--tawn-surface)', border: isUser ? 'none' : '1px solid var(--tawn-line)', color: isUser ? '#fff' : 'var(--tawn-text)', fontSize: 14, lineHeight: 1.65 }}>
        <div ref={contentRef} className="tawn-md" />
        {streaming && <span style={{ display: 'inline-block', width: 7, height: 13, background: 'currentColor', marginLeft: 2, opacity: 0.55, verticalAlign: 'text-bottom', animation: 'tawn-pulse 0.8s ease-in-out infinite' }} />}
      </div>
      {time && <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', marginTop: 5, marginLeft: isUser ? 0 : 3, marginRight: isUser ? 3 : 0 }}>{time}</span>}
    </div>
  )
}
