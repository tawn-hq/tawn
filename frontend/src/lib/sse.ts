export interface ChatAction {
  kind: string
  label: string
  path?: string
  name?: string
  description?: string
}

export interface ToolTrace {
  name: string
  arguments: Record<string, unknown>
  ok: boolean | null
  result: string
}

export interface ChatChunk {
  text: string
  done?: boolean
  tokens_in?: number
  tokens_out?: number
  error?: string
  session_id?: string
  title?: string
  action?: ChatAction
  tool?: ToolTrace
  notice?: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export async function* streamChat(
  messages: ChatMessage[],
  sensitive = false,
  target: string | null = null,
  session_id: string | null = null,
  tools = false,
  attachments: string[] = [],
): AsyncGenerator<ChatChunk> {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ history: messages, sensitive, target, session_id, tools, attachments }),
  })

  if (!res.ok || !res.body) {
    throw new Error(`${res.status} ${res.statusText}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })

    const parts = buf.split('\n\n')
    buf = parts.pop() ?? ''

    for (const part of parts) {
      if (!part.startsWith('data: ')) continue
      try {
        const ev = JSON.parse(part.slice(6)) as { type: string; text?: string; message?: string; tokens_in?: number; tokens_out?: number; session_id?: string; title?: string; action?: ChatAction; tool?: ToolTrace }
        if (ev.type === 'session') yield { text: '', session_id: ev.session_id, title: ev.title }
        else if (ev.type === 'chunk') yield { text: ev.text ?? '' }
        else if (ev.type === 'done') yield { text: '', done: true, tokens_in: ev.tokens_in, tokens_out: ev.tokens_out }
        else if (ev.type === 'error') yield { text: '', error: ev.message }
        else if (ev.type === 'action') yield { text: '', action: ev.action }
        else if (ev.type === 'tool') yield { text: '', tool: ev.tool }
        else if (ev.type === 'notice') yield { text: '', notice: ev.message }
      } catch {
        // skip malformed lines
      }
    }
  }
}
