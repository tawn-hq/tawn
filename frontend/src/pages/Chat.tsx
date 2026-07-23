import { FormEvent, useEffect, useRef, useState, KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import AppNav from '../components/AppNav'
import { ChatBubble, Button, Checkbox } from '../ds'
import { type ChatMessage, type ChatAction, streamChat } from '../lib/sse'
import {
  listHistory, getHistorySession, type SessionMeta,
  postNote, postRecall, getBrief, postCompile, getCompileStatus,
  getStatus, getChatModels, type ModelRow,
} from '../lib/api'

function useIsMobile() {
  const [m, setM] = useState(() => typeof window !== 'undefined' && window.innerWidth < 640)
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 639px)')
    const h = (e: MediaQueryListEvent) => setM(e.matches)
    mq.addEventListener('change', h)
    return () => mq.removeEventListener('change', h)
  }, [])
  return m
}

// ── Slash commands ────────────────────────────────────────────────────────────

interface SlashCmd {
  cmd: string
  args?: string
  desc: string
}

const SLASH_CMDS: SlashCmd[] = [
  { cmd: '/note', args: '<text>', desc: 'save a note to memory' },
  { cmd: '/recall', args: '<query>', desc: 'search compiled memory' },
  { cmd: '/brief', args: '[domain]', desc: 'domain summary (entities, chunks)' },
  { cmd: '/compile', desc: 'run incremental compiler' },
  { cmd: '/compile --status', desc: 'show compile status' },
  { cmd: '/compile --rebuild', desc: 'force-reprocess all files' },
  { cmd: '/export', args: '[format]', desc: 'export memory (both|jsonl|markdown)' },
  { cmd: '/status', desc: 'system health check' },
  { cmd: '/grants', desc: 'open grants settings' },
  { cmd: '/profile', desc: 'open personality settings' },
  { cmd: '/agents', desc: 'open agents page' },
  { cmd: '/federation', args: 'sources|merge', desc: 'federation operations' },
  { cmd: '/web', desc: 'show tawn URL + public ngrok link if active' },
  { cmd: '/help', desc: 'show all commands' },
]

function matchCmds(input: string): SlashCmd[] {
  const q = input.toLowerCase()
  return SLASH_CMDS.filter((c) => c.cmd.startsWith(q) || (c.cmd + ' ' + (c.args ?? '')).includes(q))
}

// ── Command palette dropdown ──────────────────────────────────────────────────

function CommandPalette({ input, onSelect }: { input: string; onSelect: (cmd: string) => void }) {
  const matches = matchCmds(input)
  if (!matches.length) return null
  return (
    <div style={{ position: 'absolute', bottom: 'calc(100% + 6px)', left: 0, right: 0, background: 'var(--tawn-surface)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', overflow: 'hidden', zIndex: 30, boxShadow: '0 4px 16px rgba(0,0,0,0.15)' }}>
      {matches.slice(0, 8).map((c) => (
        <div
          key={c.cmd + (c.args ?? '')}
          onClick={() => onSelect(c.args ? c.cmd + ' ' : c.cmd)}
          style={{ padding: '9px 14px', cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'baseline', borderBottom: '1px solid var(--tawn-line)' }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--tawn-raised)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
        >
          <span style={{ fontSize: 13, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-lapis)', fontWeight: 600, whiteSpace: 'nowrap' }}>{c.cmd}</span>
          {c.args && <span style={{ fontSize: 12, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)' }}>{c.args}</span>}
          <span style={{ fontSize: 12, color: 'var(--tawn-text-2)', marginLeft: 'auto' }}>{c.desc}</span>
        </div>
      ))}
    </div>
  )
}

// ── History sidebar ───────────────────────────────────────────────────────────

function SessionRow({ s, isActive, onSelect }: { s: SessionMeta; isActive: boolean; onSelect: () => void }) {
  const [hover, setHover] = useState(false)
  const title = (s as SessionMeta & { title?: string }).title || `session ${s.id.slice(0, 8)}`
  return (
    <div
      onClick={onSelect}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ padding: '10px 12px', borderRadius: 8, cursor: 'pointer', background: isActive ? 'var(--tawn-lapis-soft)' : hover ? 'var(--tawn-raised)' : 'transparent' }}
    >
      <div style={{ fontSize: 13, color: isActive ? 'var(--tawn-lapis)' : 'var(--tawn-text)', fontWeight: isActive ? 600 : 400, marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={title}>
        {title}
      </div>
      <div style={{ fontSize: 11, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>
        {s.turns} turns · {s.last.slice(0, 10)}
      </div>
    </div>
  )
}

function HistoryPanel({ sessions, activeId, onSelect, onNewChat, onClose }: { sessions: SessionMeta[]; activeId: string | null; onSelect: (id: string) => void; onNewChat: () => void; onClose?: () => void }) {
  return (
    <div style={{ width: '100%', height: '100%', padding: '16px 12px', display: 'flex', flexDirection: 'column', gap: 4, overflowY: 'auto', boxSizing: 'border-box' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 4px 10px' }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--tawn-text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>history</span>
        {onClose && (
          <button onClick={onClose} aria-label="close history" style={{ background: 'none', border: 'none', fontSize: 16, cursor: 'pointer', color: 'var(--tawn-text-3)', lineHeight: 1, padding: '2px 4px' }}>✕</button>
        )}
      </div>
      <Button variant="secondary" size="sm" onClick={onNewChat} style={{ margin: '0 4px 10px', justifyContent: 'flex-start' }}>+ new chat</Button>
      {sessions.map((s) => (
        <SessionRow key={s.id} s={s} isActive={s.id === activeId} onSelect={() => onSelect(s.id)} />
      ))}
      {sessions.length === 0 && <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', padding: '0 4px' }}>no history yet</p>}
    </div>
  )
}

/** History icon for the collapsed/closed toggle button. */
function HistoryIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3v5h5" /><path d="M3.05 13A9 9 0 1 0 6 5.3L3 8" /><path d="M12 7v5l4 2" />
    </svg>
  )
}

// ── Mode menu ─────────────────────────────────────────────────────────────────

function ModeMenu({ sensitive, setSensitive, webSearch, setWebSearch }: { sensitive: boolean; setSensitive: (v: boolean) => void; webSearch: boolean; setWebSearch: (v: boolean) => void }) {
  const [open, setOpen] = useState(false)
  const count = (sensitive ? 1 : 0) + (webSearch ? 1 : 0)
  return (
    <div style={{ position: 'relative', alignSelf: 'center' }}>
      <Button type="button" variant="secondary" size="sm" onClick={() => setOpen(!open)}>
        mode{count > 0 ? ` · ${count}` : ''} {open ? '▴' : '▾'}
      </Button>
      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 19 }} />
          <div style={{ position: 'absolute', bottom: 'calc(100% + 8px)', left: 0, zIndex: 20, background: 'var(--tawn-surface)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', padding: 10, minWidth: 200, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <Checkbox label="sensitive" hint="blocks cloud models" checked={sensitive} onChange={(e) => setSensitive(e.target.checked)} />
            <Checkbox label="search the web" hint="adds cited sources" checked={webSearch} onChange={(e) => setWebSearch(e.target.checked)} />
          </div>
        </>
      )}
    </div>
  )
}

// ── Model picker ──────────────────────────────────────────────────────────────

function ModelPicker({ models, target, setTarget }: { models: ModelRow[]; target: string | null; setTarget: (t: string | null) => void }) {
  const [open, setOpen] = useState(false)
  const label = target ? target.split('/').slice(-1)[0] : 'auto'
  return (
    <div style={{ position: 'relative', alignSelf: 'center' }}>
      <Button type="button" variant="secondary" size="sm" onClick={() => setOpen(!open)}>
        {label} {open ? '▴' : '▾'}
      </Button>
      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 19 }} />
          <div style={{ position: 'absolute', bottom: 'calc(100% + 8px)', left: 0, zIndex: 20, background: 'var(--tawn-surface)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', overflow: 'hidden', minWidth: 260, maxHeight: 280, overflowY: 'auto', boxShadow: '0 4px 16px rgba(0,0,0,0.15)' }}>
            <div
              onClick={() => { setTarget(null); setOpen(false) }}
              style={{ padding: '9px 14px', cursor: 'pointer', borderBottom: '1px solid var(--tawn-line)', fontSize: 13, color: !target ? 'var(--tawn-lapis)' : 'var(--tawn-text-2)', fontWeight: !target ? 600 : 400, background: !target ? 'var(--tawn-lapis-soft)' : 'transparent' }}
            >
              auto <span style={{ fontSize: 11, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>best available</span>
            </div>
            {models.map((m) => (
              <div
                key={m.target}
                onClick={() => { setTarget(m.target); setOpen(false) }}
                style={{ padding: '9px 14px', cursor: 'pointer', borderBottom: '1px solid var(--tawn-line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: target === m.target ? 'var(--tawn-lapis-soft)' : 'transparent' }}
                onMouseEnter={(e) => { if (target !== m.target) e.currentTarget.style.background = 'var(--tawn-raised)' }}
                onMouseLeave={(e) => { if (target !== m.target) e.currentTarget.style.background = 'transparent' }}
              >
                <span style={{ fontSize: 13, fontFamily: 'var(--tawn-font-mono)', color: target === m.target ? 'var(--tawn-lapis)' : 'var(--tawn-text)', fontWeight: target === m.target ? 600 : 400 }}>{m.model}</span>
                <span style={{ fontSize: 11, color: m.locality === 'local' ? 'var(--tawn-good)' : 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>{m.locality === 'local' ? 'local' : m.provider}</span>
              </div>
            ))}
            {models.length === 0 && (
              <div style={{ padding: '12px 14px', fontSize: 12, color: 'var(--tawn-text-3)' }}>no models — add a key in settings</div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ── Action card ───────────────────────────────────────────────────────────────

function ActionCard({ action, onApprove, onReject, done }: {
  action: ChatAction
  onApprove: () => void
  onReject: () => void
  done?: 'approved' | 'rejected' | 'running'
}) {
  const iconMap: Record<string, string> = {
    grant_read: '📂',
    create_domain: '🧩',
    compile: '⚙️',
    federation_scan: '🔄',
  }
  const icon = iconMap[action.kind] ?? '▶'
  return (
    <div style={{ margin: '8px 0', padding: '12px 16px', background: 'var(--tawn-surface)', border: '1px solid var(--tawn-lapis)', borderRadius: 10, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
      <span style={{ fontSize: 18 }}>{icon}</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--tawn-text)', marginBottom: 2 }}>{action.label}</div>
        {action.path && <div style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)' }}>{action.path}</div>}
        {action.name && <div style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)' }}>{action.name}{action.description ? ` — ${action.description}` : ''}</div>}
      </div>
      {done === 'running' && <span style={{ fontSize: 12, color: 'var(--tawn-text-3)' }}>running…</span>}
      {done === 'approved' && <span style={{ fontSize: 12, color: 'var(--tawn-good)' }}>✓ approved</span>}
      {done === 'rejected' && <span style={{ fontSize: 12, color: 'var(--tawn-text-3)' }}>✕ rejected</span>}
      {!done && (
        <div style={{ display: 'flex', gap: 6 }}>
          <Button size="sm" onClick={onApprove}>approve</Button>
          <Button size="sm" variant="secondary" onClick={onReject}>reject</Button>
        </div>
      )}
    </div>
  )
}

// ── Message types ─────────────────────────────────────────────────────────────

type Msg = { role: 'user' | 'assistant' | 'system'; content: string; streaming?: boolean; time?: string }
type PendingAction = { action: ChatAction; state: 'pending' | 'running' | 'approved' | 'rejected'; id: string }

// ── Main chat ─────────────────────────────────────────────────────────────────

export default function Chat() {
  const navigate = useNavigate()
  const mobile = useIsMobile()
  const [historyOpen, setHistoryOpen] = useState(() => typeof window !== 'undefined' && window.innerWidth >= 640)
  const [sessions, setSessions] = useState<SessionMeta[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [sensitive, setSensitive] = useState(false)
  const [webSearch, setWebSearch] = useState(false)
  const [target, setTarget] = useState<string | null>(null)
  const [models, setModels] = useState<ModelRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showPalette, setShowPalette] = useState(false)
  const [attachments, setAttachments] = useState<{ name: string; content: string }[]>([])
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listHistory().then(setSessions).catch(() => {})
    getChatModels().then(setModels).catch(() => {})
    // Pick up "continue in chat" payload from federation viewer
    const stored = sessionStorage.getItem('tawn_continue_history')
    if (stored) {
      sessionStorage.removeItem('tawn_continue_history')
      try {
        const history = JSON.parse(stored) as Array<{ role: string; content: string }>
        const msgs: Msg[] = history.map((h) => ({ role: h.role as 'user' | 'assistant', content: h.content }))
        setMessages(msgs)
        // summarize first user turn as starting context note
        const firstUser = history.find((h) => h.role === 'user')
        if (firstUser) {
          setMessages((prev) => [
            { role: 'system', content: `continued from federation history — ${history.length} turns loaded` },
            ...prev,
          ])
        }
      } catch { /* ignore */ }
    }
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // show palette when input starts with /
  useEffect(() => {
    setShowPalette(input.startsWith('/') && input.length > 0)
  }, [input])

  async function loadSession(id: string) {
    setActiveId(id)
    if (mobile) setHistoryOpen(false)
    try {
      const entries = await getHistorySession(id)
      setMessages(entries.map((e) => ({ role: e.role as 'user' | 'assistant', content: e.content, time: e.ts.slice(11, 16) })))
    } catch {
      setMessages([])
    }
  }

  function newChat() {
    if (mobile) setHistoryOpen(false)
    setActiveId(null)
    setMessages([])
    setError(null)
    setAttachments([])
  }

  function pushSystem(text: string) {
    setMessages((prev) => [...prev, { role: 'system', content: text }])
  }

  // ── @file attachment ──────────────────────────────────────────────────────

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    files.forEach((file) => {
      const reader = new FileReader()
      reader.onload = () => {
        const content = reader.result as string
        setAttachments((prev) => [...prev, { name: file.name, content }])
        // also inject @filename into input
        setInput((prev) => prev.replace(/@\S*$/, '') + `@${file.name} `)
      }
      reader.readAsText(file)
    })
    e.target.value = ''
  }

  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const val = e.target.value
    setInput(val)
    // trigger file picker when @ is typed at end
    if (val.endsWith('@')) {
      fileRef.current?.click()
    }
  }

  // ── Slash command execution ───────────────────────────────────────────────

  async function execSlash(raw: string): Promise<boolean> {
    const trimmed = raw.trim()
    const low = trimmed.toLowerCase()

    if (low === '/help') {
      pushSystem(
        SLASH_CMDS.map((c) => `${c.cmd}${c.args ? ' ' + c.args : ''}  —  ${c.desc}`).join('\n')
      )
      return true
    }

    if (low.startsWith('/web')) {
      try {
        const [host, tunnel] = await Promise.all([
          fetch('/api/setup/host').then((r) => r.json()) as Promise<{ ok: boolean }>,
          fetch('/api/setup/tunnel').then((r) => r.json()) as Promise<{ active: boolean; url: string | null }>,
        ])
        const local = host.ok ? 'http://tawn:8787' : 'http://127.0.0.1:8787'
        let msg = `local  → ${local}`
        if (tunnel.active && tunnel.url) msg += `\npublic → ${tunnel.url}  (shareable — anyone with this URL can access your twin)`
        else msg += '\npublic → no ngrok tunnel  (run: ngrok http 8787)'
        pushSystem(msg)
      } catch (e) {
        pushSystem(`error: ${e}`)
      }
      return true
    }

    if (low === '/status') {
      try {
        const s = await getStatus()
        pushSystem(`status: ${s.initialized ? 'initialized ✓' : 'not initialized — run tawn init'}`)
      } catch (e) {
        pushSystem(`error: ${e}`)
      }
      return true
    }

    if (low === '/grants') { navigate('/settings'); return true }
    if (low === '/profile') { navigate('/settings'); return true }
    if (low === '/agents') { navigate('/agents'); return true }

    if (low.startsWith('/note')) {
      const text = trimmed.slice(5).trim()
      if (!text) { pushSystem('/note <text> — provide text to save'); return true }
      try {
        const r = await postNote(text)
        pushSystem(`note saved → ${r.path}${r.compile_queued ? ' · compile queued' : ''}`)
      } catch (e) {
        pushSystem(`error saving note: ${e}`)
      }
      return true
    }

    if (low.startsWith('/recall')) {
      const query = trimmed.slice(7).trim()
      if (!query) { pushSystem('/recall <query> — provide a search query'); return true }
      try {
        const r = await postRecall(query, 5, undefined, 'snippets')
        if (r.chunks?.length) {
          const out = r.chunks.map((c, i) => `[${i + 1}] ${c.domain ?? '?'} — ${c.content.slice(0, 200)}${c.content.length > 200 ? '…' : ''}`).join('\n\n')
          pushSystem(`recall: "${query}"\n\n${out}`)
        } else {
          pushSystem(`recall: no results for "${query}"`)
        }
      } catch (e) {
        pushSystem(`error: ${e}`)
      }
      return true
    }

    if (low.startsWith('/brief')) {
      const domain = trimmed.slice(6).trim() || '*'
      try {
        const r = await getBrief(domain)
        pushSystem(`brief: ${r.domain}\n${r.summary}\n\nentities: ${r.entity_count} · chunks: ${r.chunk_count}${r.last_compiled ? ' · compiled: ' + r.last_compiled.slice(0, 10) : ''}`)
      } catch (e) {
        pushSystem(`error: ${e}`)
      }
      return true
    }

    if (low === '/compile --status') {
      try {
        const r = await getCompileStatus()
        pushSystem(`compile: ${r.pending ? 'running…' : 'idle'}${r.last_compiled ? ' · last: ' + r.last_compiled.slice(0, 16) : ''}`)
      } catch (e) {
        pushSystem(`error: ${e}`)
      }
      return true
    }

    if (low.startsWith('/compile')) {
      try {
        const r = await postCompile()
        pushSystem(`compile done — ${r.files_processed} files · ${r.chunks_added} chunks added · ${r.entities_resolved} entities${r.error ? '\nerror: ' + r.error : ''}`)
      } catch (e) {
        pushSystem(`error: ${e}`)
      }
      return true
    }

    if (low.startsWith('/export')) {
      const fmt = trimmed.slice(7).trim() || 'both'
      window.open(`/api/export?format=${encodeURIComponent(fmt)}`, '_blank')
      pushSystem(`export started (format: ${fmt})`)
      return true
    }

    if (low.startsWith('/federation')) {
      const sub = trimmed.slice(11).trim()
      if (sub === 'sources' || sub === '') {
        try {
          const sources = await fetch('/api/federation/sources').then((r) => r.json()) as { name: string; path: string; adapter: string | null }[]
          if (sources.length) {
            pushSystem('federation sources:\n' + sources.map((s) => `• ${s.name}: ${s.path} [${s.adapter ?? 'auto'}]`).join('\n'))
          } else {
            pushSystem('no federation sources — add one in agents page')
          }
        } catch (e) {
          pushSystem(`error: ${e}`)
        }
        return true
      }
      if (sub === 'merge') {
        try {
          await fetch('/api/federation/merge', { method: 'POST' })
          pushSystem('federation merge triggered')
        } catch (e) {
          pushSystem(`error: ${e}`)
        }
        return true
      }
      pushSystem('federation: sources | merge')
      return true
    }

    return false
  }

  // ── Action approval ───────────────────────────────────────────────────────

  async function executeAction(id: string, action: ChatAction, approved: boolean) {
    if (!approved) {
      setPendingActions((prev) => prev.map((a) => a.id === id ? { ...a, state: 'rejected' } : a))
      setMessages((prev) => [...prev, { role: 'user', content: `[rejected: ${action.label}]` }])
      return
    }
    setPendingActions((prev) => prev.map((a) => a.id === id ? { ...a, state: 'running' } : a))
    try {
      const resp = await fetch('/api/chat/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(action),
      })
      const text = await resp.text()
      let result: { ok: boolean; message?: string; error?: string; chunks_added?: number; name?: string }
      try {
        result = JSON.parse(text)
      } catch {
        result = { ok: false, error: `server error: ${text.slice(0, 120)}` }
      }
      if (!resp.ok && result.ok === undefined) result = { ok: false, error: `HTTP ${resp.status}` }
      setPendingActions((prev) => prev.map((a) => a.id === id ? { ...a, state: 'approved' } : a))
      if (result.ok) {
        const msg = result.message ?? result.name ?? `${action.kind} done${result.chunks_added != null ? ` · ${result.chunks_added} chunks` : ''}`
        setMessages((prev) => [...prev, { role: 'system', content: `✓ ${msg}` }])
      } else {
        setMessages((prev) => [...prev, { role: 'system', content: `✗ ${action.kind} failed: ${result.error ?? 'unknown error'}` }])
      }
    } catch (err) {
      setPendingActions((prev) => prev.map((a) => a.id === id ? { ...a, state: 'rejected' } : a))
      setMessages((prev) => [...prev, { role: 'system', content: `error: ${err}` }])
    }
  }

  // ── Send ──────────────────────────────────────────────────────────────────

  async function send(e: FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setShowPalette(false)
    setError(null)

    // slash command?
    if (text.startsWith('/')) {
      await execSlash(text)
      return
    }

    // build content with attachments
    let content = text
    if (attachments.length) {
      const atBlock = attachments.map((a) => `[attached: ${a.name}]\n${a.content}`).join('\n\n---\n\n')
      content = `${atBlock}\n\n---\n\n${text}`
      setAttachments([])
    }

    const userMsg: Msg = { role: 'user', content: text } // show clean text in UI
    const apiMsg: ChatMessage = { role: 'user', content } // full content with attachments to API
    const history = [...messages.filter((m) => m.role !== 'system' && !m.streaming).map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content })), apiMsg]
    setMessages((prev) => [...prev, userMsg, { role: 'assistant', content: '', streaming: true }])
    setPendingActions([])
    setBusy(true)

    try {
      let acc = ''
      for await (const chunk of streamChat(history, sensitive, target, activeId)) {
        if (chunk.session_id && chunk.session_id !== activeId) {
          setActiveId(chunk.session_id)
          const title = chunk.title ?? 'chat'
          setSessions((prev) => {
            const exists = prev.find((s) => s.id === chunk.session_id)
            if (exists) return prev
            return [{ id: chunk.session_id!, title, started: new Date().toISOString(), last: new Date().toISOString(), turns: 1, model: '' } as SessionMeta & { title: string }, ...prev]
          })
          continue
        }
        if (chunk.error) { setError(chunk.error); break }
        if (chunk.action) {
          const id = `${chunk.action.kind}-${Date.now()}`
          setPendingActions((prev) => [...prev, { action: chunk.action!, state: 'pending', id }])
          continue
        }
        acc += chunk.text ?? ''
        setMessages((prev) => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          if (last?.streaming) copy[copy.length - 1] = { ...last, content: acc, streaming: !chunk.done }
          return copy
        })
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'unknown error')
      setMessages((prev) => prev.filter((m) => !m.streaming))
    } finally {
      setBusy(false)
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send(e as unknown as FormEvent)
    }
    if (e.key === 'Escape') setShowPalette(false)
  }

  return (
    <div style={{ background: 'var(--tawn-bg)', display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <AppNav />
      <input ref={fileRef} type="file" multiple style={{ display: 'none' }} onChange={handleFileChange} />
      <div style={{ flex: 1, display: 'flex', minHeight: 0, maxWidth: 1040, width: '100%', margin: '0 auto', position: 'relative' }}>
        {/* Desktop: normal flex column that collapses to 0 width — panel
            stays in the layout flow, nothing overlaps. Mobile: fixed overlay
            with a backdrop, since there's no spare width to shift into. */}
        {mobile ? (
          historyOpen && (
            <>
              <div onClick={() => setHistoryOpen(false)} style={{ position: 'fixed', inset: 0, top: 56, background: 'rgba(0,0,0,0.4)', zIndex: 29 }} />
              <div style={{ position: 'fixed', top: 56, bottom: 0, left: 0, width: 'min(280px, 84vw)', background: 'var(--tawn-bg)', borderRight: '1px solid var(--tawn-line)', zIndex: 30, boxShadow: '2px 0 16px rgba(0,0,0,0.15)' }}>
                <HistoryPanel sessions={sessions} activeId={activeId} onSelect={loadSession} onNewChat={newChat} onClose={() => setHistoryOpen(false)} />
              </div>
            </>
          )
        ) : (
          <div style={{ width: historyOpen ? 240 : 0, flexShrink: 0, overflow: 'hidden', borderRight: historyOpen ? '1px solid var(--tawn-line)' : 'none', transition: 'width 0.18s ease' }}>
            <div style={{ width: 240 }}>
              <HistoryPanel sessions={sessions} activeId={activeId} onSelect={loadSession} onNewChat={newChat} />
            </div>
          </div>
        )}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, padding: mobile ? '12px 16px 0' : '16px 24px 0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <button
              onClick={() => setHistoryOpen(!historyOpen)}
              aria-label={historyOpen ? 'hide history' : 'show history'}
              title={historyOpen ? 'hide history' : 'show history'}
              style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, flexShrink: 0, border: '1px solid var(--tawn-line)', borderRadius: 7, background: historyOpen ? 'var(--tawn-lapis-soft)' : 'var(--tawn-surface)', color: historyOpen ? 'var(--tawn-lapis)' : 'var(--tawn-text-2)', cursor: 'pointer' }}
            >
              <HistoryIcon />
            </button>
            <div style={{ fontSize: 12, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>
              {activeId ? `session ${activeId.slice(0, 8)}` : 'new chat'}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            {/* spacer pushes messages to bottom when chat is short */}
            <div style={{ flex: 1 }} />
            {messages.length === 0 && (
              <div style={{ textAlign: 'center', padding: '40px 0' }}>
                <div style={{ fontSize: 13, color: 'var(--tawn-text-3)', marginBottom: 10 }}>ask your twin anything — it recalls across all four domains.</div>
                <div style={{ fontSize: 11, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>type / for commands · @ to attach a file</div>
              </div>
            )}
            {messages.map((m, i) => {
              if (m.role === 'system') {
                return (
                  <div key={i} style={{ margin: '8px 0', padding: '10px 14px', background: 'var(--tawn-surface)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', fontSize: 12, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-2)', whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
                    {m.content}
                  </div>
                )
              }
              return <ChatBubble key={i} role={m.role} streaming={m.streaming} time={m.time}>{m.content}</ChatBubble>
            })}
            {pendingActions.map((pa) => (
              <ActionCard
                key={pa.id}
                action={pa.action}
                done={pa.state !== 'pending' ? pa.state as 'running' | 'approved' | 'rejected' : undefined}
                onApprove={() => executeAction(pa.id, pa.action, true)}
                onReject={() => executeAction(pa.id, pa.action, false)}
              />
            ))}
            {error && <p style={{ color: 'var(--tawn-crit)', fontSize: 13, marginBottom: 8 }}>{error}</p>}
            <div ref={bottomRef} />
          </div>

          {/* attachment pills */}
          {attachments.length > 0 && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', padding: '8px 0 4px' }}>
              {attachments.map((a, i) => (
                <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, fontFamily: 'var(--tawn-font-mono)', padding: '3px 8px', background: 'var(--tawn-lapis-soft)', color: 'var(--tawn-lapis)', borderRadius: 999, border: '1px solid var(--tawn-lapis)' }}>
                  @{a.name}
                  <span onClick={() => setAttachments((prev) => prev.filter((_, j) => j !== i))} style={{ cursor: 'pointer', color: 'var(--tawn-text-3)', lineHeight: 1 }}>✕</span>
                </span>
              ))}
            </div>
          )}

          <form onSubmit={send} style={{ position: 'relative', display: 'flex', gap: 8, alignItems: 'flex-end', borderTop: '1px solid var(--tawn-line)', padding: '14px 0', marginTop: 12 }}>
            {showPalette && <CommandPalette input={input} onSelect={(cmd) => setInput(cmd)} />}
            <ModelPicker models={models} target={target} setTarget={setTarget} />
            <ModeMenu sensitive={sensitive} setSensitive={setSensitive} webSearch={webSearch} setWebSearch={setWebSearch} />
            <textarea
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Message your twin… (/ for commands · @ to attach)"
              rows={2}
              disabled={busy}
              style={{ flex: 1, fontFamily: 'var(--tawn-font-sans)', fontSize: 14, padding: '9px 12px', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius-sm)', background: 'var(--tawn-raised)', color: 'var(--tawn-text)', resize: 'none', outline: 'none', lineHeight: 1.5, boxSizing: 'border-box' }}
            />
            <Button type="submit" disabled={busy || !input.trim()}>
              {busy ? '…' : 'send'}
            </Button>
          </form>
          <p style={{ fontSize: 12, color: 'var(--tawn-text-3)', padding: '0 0 16px', fontFamily: 'var(--tawn-font-mono)' }}>
            enter to send · shift+enter newline · @ attach file · / commands
          </p>
        </div>
      </div>
    </div>
  )
}
