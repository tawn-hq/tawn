import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { marked } from 'marked'
import AppNav from '../components/AppNav'
import { Button, Badge } from '../ds'
import { renderDiagramsIn } from '../lib/diagrams'

marked.setOptions({ breaks: true })

interface ConvTurn { role: string; content: string; ts: string; model?: string | null }
interface ConvDetail { id: number; source: string; project: string | null; domain: string | null; source_path: string; turns: ConvTurn[]; error?: string }

const DOMAINS = ['work', 'wealth', 'research', 'academic', 'hobby'] as const
type Domain = typeof DOMAINS[number]

function TurnBubble({ turn }: { turn: ConvTurn }) {
  const isUser = turn.role === 'user' || turn.role === 'human'
  const isThinking = turn.role === 'thinking'
  const contentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!contentRef.current) return
    contentRef.current.innerHTML = marked.parse(turn.content) as string
    renderDiagramsIn(contentRef.current)
  }, [turn.content])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start' }}>
      <div style={{ fontSize: 10, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', marginBottom: 4, paddingLeft: isUser ? 0 : 4 }}>
        {isThinking ? '◈ thinking' : isUser ? 'you' : turn.role}
        {turn.model && ` · ${turn.model}`}
        {turn.ts && ` · ${turn.ts.slice(0, 16)}`}
      </div>
      <div
        ref={contentRef}
        className="tawn-md"
        style={{
          maxWidth: '88%', padding: '10px 14px',
          background: isUser ? 'var(--tawn-lapis-soft)' : isThinking ? 'var(--tawn-raised)' : 'var(--tawn-surface)',
          border: `1px solid ${isUser ? 'var(--tawn-lapis)' : 'var(--tawn-line)'}`,
          borderRadius: isUser ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
          fontSize: 13, lineHeight: 1.65,
          color: isThinking ? 'var(--tawn-text-3)' : 'var(--tawn-text)',
          fontStyle: isThinking ? 'italic' : 'normal',
          wordBreak: 'break-word',
        }}
      />
    </div>
  )
}

export default function AgentConversation() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [conv, setConv] = useState<ConvDetail | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!id) return
    setConv(null)
    setError('')
    fetch(`/api/federation/conversations/${id}`)
      .then((r) => r.json())
      .then(setConv)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
  }, [id])

  function continueInChat() {
    if (!conv) return
    const history = conv.turns
      .filter((t) => t.role === 'user' || t.role === 'human' || t.role === 'assistant')
      .map((t) => ({ role: t.role === 'human' ? 'user' : t.role, content: t.content }))
    sessionStorage.setItem('tawn_continue_history', JSON.stringify(history))
    navigate('/chat')
  }

  const userTurns = conv?.turns.filter((t) => t.role === 'user' || t.role === 'human') || []
  const title = userTurns[0]?.content.slice(0, 90) || conv?.source_path.split('/').pop() || 'conversation'
  const dom = conv && DOMAINS.includes(conv.domain as Domain) ? conv.domain as Domain : undefined

  return (
    <div style={{ background: 'var(--tawn-bg)', minHeight: '100vh' }}>
      <AppNav />
      <div style={{ maxWidth: 820, margin: '0 auto', padding: '24px 24px 80px' }}>
        <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
          <Button variant="secondary" size="sm" onClick={() => navigate('/agents')}>← back to agents</Button>
        </div>

        {error && <p style={{ color: 'var(--tawn-crit)', fontSize: 14 }}>error: {error}</p>}
        {conv?.error && <p style={{ color: 'var(--tawn-crit)', fontSize: 14 }}>error: {conv.error}</p>}

        {!conv && !error && <p style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>loading…</p>}

        {conv && (
          <>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 17, fontWeight: 600, color: 'var(--tawn-text)', marginBottom: 6, lineHeight: 1.4 }}>{title}</div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', border: '1px solid var(--tawn-line)', borderRadius: 999, padding: '2px 8px', color: 'var(--tawn-text-3)' }}>{conv.source}</span>
                {conv.project && <span style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)' }}>{conv.project}</span>}
                {dom && <Badge domain={dom}>{dom}</Badge>}
                <span style={{ fontSize: 11, color: 'var(--tawn-text-3)' }}>{conv.turns.length} turns</span>
                <Button size="sm" onClick={continueInChat}>continue in chat →</Button>
              </div>
              <div style={{ fontSize: 10, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', marginTop: 6, wordBreak: 'break-all' }}>{conv.source_path}</div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {conv.turns.length === 0 && <div style={{ fontSize: 13, color: 'var(--tawn-text-3)' }}>no turns found in this file</div>}
              {conv.turns.map((t, i) => <TurnBubble key={i} turn={t} />)}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
