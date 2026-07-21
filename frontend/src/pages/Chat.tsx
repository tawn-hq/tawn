import { FormEvent, useEffect, useRef, useState } from 'react'
import Layout from '../components/Layout'
import { type ChatMessage, streamChat } from '../lib/sse'

function Bubble({ msg }: { msg: ChatMessage & { streaming?: boolean } }) {
  const isUser = msg.role === 'user'
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: 12,
      }}
    >
      <div
        style={{
          maxWidth: '75%',
          padding: '10px 14px',
          borderRadius: isUser ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
          background: isUser ? 'var(--lapis)' : 'var(--bg-raised)',
          color: isUser ? '#fff' : 'var(--text)',
          fontSize: 'var(--sz-base)',
          lineHeight: 1.5,
          whiteSpace: 'pre-wrap',
        }}
      >
        {msg.content}
        {msg.streaming && (
          <span
            style={{
              display: 'inline-block',
              width: 8,
              height: 14,
              background: 'currentColor',
              marginLeft: 2,
              animation: 'blink 1s step-end infinite',
            }}
          />
        )}
      </div>
    </div>
  )
}

export default function Chat() {
  const [messages, setMessages] = useState<(ChatMessage & { streaming?: boolean })[]>([])
  const [input, setInput] = useState('')
  const [sensitive, setSensitive] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function send(e: FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setError(null)

    const userMsg: ChatMessage = { role: 'user', content: text }
    const history = [...messages.filter((m) => !m.streaming), userMsg]
    setMessages([...history, { role: 'assistant', content: '', streaming: true }])
    setBusy(true)

    try {
      let acc = ''
      for await (const chunk of streamChat(history, sensitive)) {
        if (chunk.error) {
          setError(chunk.error)
          break
        }
        acc += chunk.text
        setMessages([
          ...history,
          { role: 'assistant', content: acc, streaming: !chunk.done },
        ])
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'unknown error')
      setMessages(history)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Layout narrow>
      <style>{`@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }`}</style>

      <div
        style={{
          height: 'calc(100dvh - 48px - 100px)',
          overflowY: 'auto',
          padding: '8px 0 16px',
        }}
      >
        {messages.length === 0 && (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: 80 }}>
            Start a conversation with your twin.
          </p>
        )}
        {messages.map((m, i) => (
          <Bubble key={i} msg={m} />
        ))}
        {error && (
          <p style={{ color: 'var(--error)', fontSize: 'var(--sz-sm)', marginTop: 8 }}>
            {error}
          </p>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={send}
        style={{
          display: 'flex',
          gap: 8,
          alignItems: 'flex-end',
          borderTop: '1px solid var(--border)',
          paddingTop: 12,
        }}
      >
        <label
          style={{ fontSize: 'var(--sz-sm)', color: 'var(--text-muted)', whiteSpace: 'nowrap', alignSelf: 'center' }}
        >
          <input
            type="checkbox"
            checked={sensitive}
            onChange={(e) => setSensitive(e.target.checked)}
            style={{ marginRight: 4 }}
          />
          sensitive
        </label>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send(e as unknown as FormEvent)
            }
          }}
          placeholder="Message your twin…"
          rows={2}
          disabled={busy}
          style={{
            flex: 1,
            resize: 'none',
            border: '1px solid var(--border)',
            borderRadius: 'var(--r)',
            padding: '8px 12px',
            background: 'var(--bg-raised)',
            color: 'var(--text)',
            fontFamily: 'var(--font)',
            fontSize: 'var(--sz-base)',
          }}
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          style={{
            padding: '8px 18px',
            background: 'var(--lapis)',
            color: '#fff',
            border: 'none',
            borderRadius: 'var(--r)',
            fontWeight: 600,
            cursor: busy ? 'not-allowed' : 'pointer',
            opacity: busy || !input.trim() ? 0.5 : 1,
          }}
        >
          {busy ? '…' : 'send'}
        </button>
      </form>

      <div style={{ marginTop: 8, display: 'flex', gap: 12, fontSize: 'var(--sz-sm)', color: 'var(--text-muted)' }}>
        <button
          onClick={() => setMessages([])}
          style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 'var(--sz-sm)' }}
        >
          /new
        </button>
        <span>shift+enter for newline</span>
      </div>
    </Layout>
  )
}
