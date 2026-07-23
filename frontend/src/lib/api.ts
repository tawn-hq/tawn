async function _fetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${text}`)
  }
  return res.json() as Promise<T>
}

// ── Status & domains ──────────────────────────────────────────────────────────

export interface Status {
  initialized: boolean
}

export interface DomainRow {
  name: string
  label: string
  nav: boolean
}

export const getStatus = (): Promise<Status> => _fetch('/api/status')
export const getDomains = (): Promise<DomainRow[]> => _fetch('/api/domains')

// ── Setup ─────────────────────────────────────────────────────────────────────

export const postSetupInit = (): Promise<{ created: string[] }> =>
  _fetch('/api/setup/init', { method: 'POST' })

export const postSetupDb = (): Promise<{ server_up: boolean; can_connect: boolean; detail: string }> =>
  _fetch('/api/setup/db', { method: 'POST' })

export const getSetupModels = (): Promise<{ name: string; size_gb: number; fits: boolean; recommended: boolean }[]> =>
  _fetch('/api/setup/models')

export const getKeyStatus = (provider: string): Promise<{ status: string }> =>
  _fetch(`/api/setup/keys/${provider}`)

export const postKey = (provider: string, key: string): Promise<{ ok: boolean }> =>
  _fetch(`/api/setup/keys/${provider}`, { method: 'POST', body: JSON.stringify({ key }) })

export const getSetupHost = (): Promise<{ ok: boolean; hint: string }> =>
  _fetch('/api/setup/host')

export const getSetupTunnel = (): Promise<{ url: string | null; active: boolean }> =>
  _fetch('/api/setup/tunnel')

// ── Grants + audit ────────────────────────────────────────────────────────────

export interface Grants {
  read: string[]
  write: string[]
  observe: string[]
  system: boolean
  mcp: string[]
}

export const getGrants = (): Promise<Grants> => _fetch('/api/grants')
export const putGrants = (grants: Grants): Promise<{ ok: boolean }> =>
  _fetch('/api/grants', { method: 'PUT', body: JSON.stringify(grants) })
export const confirmGrants = (): Promise<{ ok: boolean; error?: string }> =>
  _fetch('/api/grants/confirm', { method: 'POST' })

export interface AuditEntry {
  ts: string
  op: string
  target: string
  ok: boolean
  detail: string
  chain: string
  actor?: string   // absent on entries written before the actor field existed
}

export interface AuditPage {
  total: number
  entries: AuditEntry[]
}
export const getAudit = (limit = 100, offset = 0): Promise<AuditPage> =>
  _fetch(`/api/audit?limit=${limit}&offset=${offset}`)
export const verifyAudit = (): Promise<{ intact: boolean }> => _fetch('/api/audit/verify')

// ── Profile ───────────────────────────────────────────────────────────────────

export interface ProfileBody {
  name: string
  role: string
  focus: string
  extra: Record<string, string>
}
export const getProfile = (): Promise<Record<string, string>> => _fetch('/api/profile')
export const putProfile = (body: ProfileBody): Promise<{ ok: boolean }> =>
  _fetch('/api/profile', { method: 'PUT', body: JSON.stringify(body) })

// ── History ───────────────────────────────────────────────────────────────────

export interface SessionMeta {
  id: string
  started: string
  last: string
  turns: number
  model: string
}
export interface HistoryEntry {
  ts: string
  role: string
  content: string
  model: string
  tokens_in: number
  tokens_out: number
}

export const listHistory = (): Promise<SessionMeta[]> => _fetch('/api/history')
export const getHistorySession = (id: string): Promise<HistoryEntry[]> =>
  _fetch(`/api/history/${id}`)

// ── All models ────────────────────────────────────────────────────────────────

export const getAllModels = (): Promise<ModelRow[]> => _fetch('/api/models')

// ── Chat ──────────────────────────────────────────────────────────────────────

export interface ModelRow {
  target: string
  provider: string
  model: string
  locality: string
}

export const getChatModels = (): Promise<ModelRow[]> => _fetch('/api/chat/models')

export type ChatEvent =
  | { type: 'chunk'; text: string }
  | { type: 'done'; tokens_in: number; tokens_out: number }
  | { type: 'error'; message: string }

export async function streamChat(
  history: { role: string; content: string }[],
  sensitive: boolean,
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  const resp = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ history, sensitive }),
  })
  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const line of parts) {
      if (!line.startsWith('data: ')) continue
      onEvent(JSON.parse(line.slice(6)) as ChatEvent)
    }
  }
}

// ── Domain create ─────────────────────────────────────────────────────────────

export interface DraftResponse {
  source?: string
  view?: unknown
  error?: string | null
  needs_wizard?: boolean
}

export const enableDomain = (name: string): Promise<{ ok: boolean }> =>
  _fetch(`/api/domains/${name}/enable`, { method: 'POST' })

export const disableDomain = (name: string): Promise<{ ok: boolean }> =>
  _fetch(`/api/domains/${name}/enable`, { method: 'DELETE' })

export const postDomainDraft = (name: string, description: string): Promise<DraftResponse> =>
  _fetch('/api/domains/draft', { method: 'POST', body: JSON.stringify({ name, description }) })

export const postDomainPromote = (name: string): Promise<{ ok: boolean }> =>
  _fetch(`/api/domains/draft/${name}/promote`, { method: 'POST' })

export const deleteDomainDraft = (name: string): Promise<{ ok: boolean }> =>
  _fetch(`/api/domains/draft/${name}`, { method: 'DELETE' })

// ── Memory ────────────────────────────────────────────────────────────────────

export interface SnippetChunk {
  id?: number
  content: string
  source: string
  domain: string | null
  score: number | null
  asof: string | null
  stale: boolean
}

export interface FeedChunk {
  id: number
  domain: string | null
  source_path: string
  source_label: string
  source_type: 'agent-memory' | 'history' | 'raw' | 'imports' | 'external'
  content: string
  content_hash: string
  priority_tier: number
  stale: boolean
  compiled_at: string | null
  asof: string | null
  chunk_index?: number
}

export interface ChunkPage {
  total: number
  offset: number
  limit: number
  source_type: string
  chunks: FeedChunk[]
}

export const getChunks = (opts?: { domain?: string; source_type?: string; limit?: number; offset?: number }): Promise<ChunkPage> => {
  const params = new URLSearchParams()
  if (opts?.domain) params.set('domain', opts.domain)
  if (opts?.source_type) params.set('source_type', opts.source_type)
  if (opts?.limit !== undefined) params.set('limit', String(opts.limit))
  if (opts?.offset !== undefined) params.set('offset', String(opts.offset))
  return _fetch(`/api/chunks?${params}`)
}

export const getChunk = (id: number): Promise<FeedChunk> => _fetch(`/api/chunks/${id}`)

export interface ChunkStats {
  total: number
  with_embeddings: number
  embed_model: string | null
  embed_dims: number | null
  by_type: { 'agent-memory': number; imports: number; history: number; raw: number }
}

export const getChunkStats = (): Promise<ChunkStats> => _fetch('/api/chunks/stats')
export const deleteChunks = (source_type: 'imports' | 'history' | 'all'): Promise<{ ok: boolean; deleted: number }> =>
  _fetch(`/api/chunks?source_type=${source_type}`, { method: 'DELETE' })

export interface RecallResult {
  format: 'snippets' | 'composed'
  query: string
  chunks?: SnippetChunk[]
  answer?: string
  sources?: string[]
  embed_error?: string
  entity_hits?: unknown[]
  searched_domains?: string[]
}

export interface BriefResult {
  domain: string
  summary: string
  entity_count: number
  chunk_count: number
  last_compiled: string | null
  staleness_hours: number | null
  stale_chunk_count: number
}

export interface CompileResult {
  ok: boolean
  files_processed: number
  chunks_added: number
  chunks_removed: number
  entities_resolved: number
  error: string | null
}

export interface CompileStatus {
  pending: boolean
  last_compiled: string | null
}

export const postNote = (
  payload: string,
  domain?: string,
  type = 'observation',
  confidence = 'medium',
): Promise<{ ok: boolean; path: string; compile_queued: boolean }> =>
  _fetch('/api/note', {
    method: 'POST',
    body: JSON.stringify({ payload, domain: domain ?? null, type, confidence }),
  })

export const postRecall = (
  query: string,
  top_k = 5,
  domain?: string,
  format: 'snippets' | 'composed' = 'snippets',
): Promise<RecallResult> =>
  _fetch('/api/recall', {
    method: 'POST',
    body: JSON.stringify({ query, top_k, domain: domain ?? null, format }),
  })

export const getBrief = (domain = '*'): Promise<BriefResult> =>
  _fetch(`/api/brief/${encodeURIComponent(domain)}`)

export const getCompileStatus = (): Promise<CompileStatus> =>
  _fetch('/api/compile/status')

export const postCompile = (): Promise<CompileResult> =>
  _fetch('/api/compile', { method: 'POST' })
