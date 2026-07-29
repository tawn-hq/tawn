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
  net: boolean
  shell: boolean
}

export interface GrantsSaved {
  ok: boolean
  confirmed: boolean
  message: string
}

export const getGrants = (): Promise<Grants> => _fetch('/api/grants')
export const putGrants = (grants: Grants): Promise<GrantsSaved> =>
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

// ── Grouped feed ──────────────────────────────────────────────────────────────

export interface GroupChunk {
  id: number
  title: string | null
  summary: string
  stale: boolean
}

export interface GroupCard {
  group_key: string
  title: string | null
  summary: string | null
  domain: string | null
  chunk_count: number
  enriched: boolean
  latest_at: string | null
  chunks: GroupChunk[]
}

export interface GroupPage {
  total: number
  offset: number
  limit: number
  groups: GroupCard[]
}

export const getGroups = (opts?: { domain?: string; limit?: number; offset?: number }): Promise<GroupPage> => {
  const params = new URLSearchParams()
  if (opts?.domain) params.set('domain', opts.domain)
  if (opts?.limit !== undefined) params.set('limit', String(opts.limit))
  if (opts?.offset !== undefined) params.set('offset', String(opts.offset))
  return _fetch(`/api/groups?${params}`)
}

// ── Wiki ──────────────────────────────────────────────────────────────────────

export interface WikiTree {
  ready: boolean
  domains: { name: string; path: string }[]
  entities: { name: string; path: string }[]
}

export interface WikiLink {
  id: number
  label: string
  relation: string
  weight: number
}

export interface WikiEntity {
  id: number
  canonical: string
  domain: string | null
  confidence: string | null
  first_seen: string | null
  related: WikiLink[]
  backlinks: WikiLink[]
}

export interface GraphNode {
  id: number
  label: string
  domain: string | null
  confidence: string | null
}

export interface GraphData {
  nodes: GraphNode[]
  links: { source: number; target: number; relation: string; weight: number }[]
  clusters?: { domain: string; count: number }[]
}

export const getWikiTree = (): Promise<WikiTree> => _fetch('/api/wiki/tree')

export const getWikiPage = (path: string): Promise<{ path: string; content: string }> =>
  _fetch(`/api/wiki/page?path=${encodeURIComponent(path)}`)

export const getWikiEntity = (name: string): Promise<WikiEntity> =>
  _fetch(`/api/wiki/entity/${encodeURIComponent(name)}`)

export const getWikiGraph = (opts?: { domain?: string; entity?: string; depth?: number; cluster?: boolean; limit?: number }): Promise<GraphData> => {
  const params = new URLSearchParams()
  if (opts?.domain) params.set('domain', opts.domain)
  if (opts?.entity) params.set('entity', opts.entity)
  if (opts?.depth !== undefined) params.set('depth', String(opts.depth))
  if (opts?.cluster) params.set('cluster', 'true')
  if (opts?.limit !== undefined) params.set('limit', String(opts.limit))
  return _fetch(`/api/wiki/graph?${params}`)
}

// ── Document reconstruction ───────────────────────────────────────────────────

export interface GroupDocument {
  group_key: string
  title: string
  summary: string | null
  domain: string | null
  body: string
  chunk_count: number
  enriched_chunks: number
  source_paths: string[]
  chunk_ids: number[]
  stale: boolean
}

export const getGroupDocument = (groupKey: string): Promise<GroupDocument> =>
  _fetch(`/api/groups/document?group_key=${encodeURIComponent(groupKey)}`)

// ── Personal notes ────────────────────────────────────────────────────────────

export interface PersonalNote {
  id: string
  note_id: string | null
  file: string
  index: number
  type: string
  domain: string | null
  confidence: string
  asof: string | null
  ttl_days: number | null
  body: string
}

export interface NotePage {
  total: number
  offset: number
  limit: number
  notes: PersonalNote[]
}

export const getNotes = (opts?: { domain?: string; limit?: number; offset?: number }): Promise<NotePage> => {
  const p = new URLSearchParams()
  if (opts?.domain) p.set('domain', opts.domain)
  if (opts?.limit !== undefined) p.set('limit', String(opts.limit))
  if (opts?.offset !== undefined) p.set('offset', String(opts.offset))
  return _fetch(`/api/notes?${p}`)
}

export const putNote = (id: string, body: { body?: string; domain?: string | null }): Promise<PersonalNote> =>
  _fetch(`/api/notes/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(body) })

export const deleteNote = (id: string): Promise<{ ok: boolean; deleted: string }> =>
  _fetch(`/api/notes/${encodeURIComponent(id)}`, { method: 'DELETE' })

// ── Enrichment ────────────────────────────────────────────────────────────────

export interface EnrichStatus {
  chunks_total: number
  chunks_enriched: number
  groups_total: number
  groups_enriched: number
  pending: number
}

export interface EnrichResult {
  ok: boolean
  chunks_enriched: number
  groups_enriched: number
  failed: number
  error: string | null
}

export const getEnrichStatus = (): Promise<EnrichStatus> => _fetch('/api/enrich/status')

export const postEnrich = (limit = 200, cloud = false): Promise<EnrichResult> =>
  _fetch('/api/enrich', { method: 'POST', body: JSON.stringify({ limit, cloud }) })

// ── Observability ─────────────────────────────────────────────────────────────

export interface AuditEvent {
  ts: string
  op: string
  target: string
  ok: boolean
  detail: string
  actor?: string
  chain: string
}

export interface EventPage {
  total: number
  offset: number
  limit: number
  entries: AuditEvent[]
}

export interface ChainStatus {
  intact: boolean
  entries: number
  first_break_index: number | null
  first_break_ts: string | null
}

export interface SpendGroup {
  operation?: string
  provider?: string
  caller?: string
  calls: number
  cost_usd: number
  unpriced: number
}

export interface SpendSummary {
  total_calls: number
  total_cost_usd: number
  unpriced_calls: number
  total_tokens_in: number
  total_tokens_out: number
  by_operation: SpendGroup[]
  by_provider: SpendGroup[]
  by_caller: SpendGroup[]
  by_day: { day: string; calls: number; cost_usd: number }[]
}

export interface SpendStatus {
  last_reconciled: string | null
  entries_seen: number
  pending_bytes: number
}

export const getEvents = (opts?: { actor?: string; op?: string; limit?: number; offset?: number }): Promise<EventPage> => {
  const p = new URLSearchParams()
  if (opts?.actor) p.set('actor', opts.actor)
  if (opts?.op) p.set('op', opts.op)
  if (opts?.limit !== undefined) p.set('limit', String(opts.limit))
  if (opts?.offset !== undefined) p.set('offset', String(opts.offset))
  return _fetch(`/api/observability/events?${p}`)
}

export const getVerify = (): Promise<ChainStatus> => _fetch('/api/observability/verify')
export const getSpend = (): Promise<SpendSummary> => _fetch('/api/observability/spend')
export const getSpendStatus = (): Promise<SpendStatus> => _fetch('/api/observability/spend/status')
export const postReconcile = (): Promise<{ entries: number; rollups: number }> =>
  _fetch('/api/observability/reconcile', { method: 'POST' })

// ── Observer ──────────────────────────────────────────────────────────────────

export interface ObserverSession {
  id: number
  project: string
  started_at: string | null
  ended_at: string | null
  closed_by: string | null
  event_count: number
  lines_added: number
  lines_removed: number
  attribution: string
  note_path: string | null
  note_state: string
}

export interface ObserverEvent {
  path: string
  kind: string
  actor: string
  confidence: string
  basis: string
  lines_added: number
  lines_removed: number
  ts: string | null
}

export const getObserverSessions = (limit = 20): Promise<{ sessions: ObserverSession[] }> =>
  _fetch(`/api/observer/sessions?limit=${limit}`)

export const getObserverEvents = (id: number): Promise<{ events: ObserverEvent[] }> =>
  _fetch(`/api/observer/sessions/${id}/events`)

export const postObserverReview = (project?: string): Promise<{ closed: number; notes_written: number }> =>
  _fetch(`/api/observer/review${project ? `?project=${encodeURIComponent(project)}` : ''}`, { method: 'POST' })

// ── Tools: MCP servers, skills, generated tools ──────────────────────────────

export interface McpServerRow {
  name: string
  transport: string
  enabled: boolean
  granted: boolean
  callable: boolean
  source: string
  env_keys: string[]
  tool_count: number
}

export interface DiscoveredServer {
  name: string
  transport: string
  source: string
  env_keys: string[]
  known: boolean
}

export interface SkillRow {
  name: string
  description: string
  body: string
  source: string
  imported_from: string | null
}

export interface GeneratedTool {
  name: string
  description: string
  capabilities: string[]
  enabled: boolean
  granted: boolean
  created_from: string
}

export const getMcpServers = (): Promise<{ servers: McpServerRow[] }> =>
  _fetch('/api/tools/mcp/servers')

export const getDiscoveredServers = (): Promise<{ servers: DiscoveredServer[] }> =>
  _fetch('/api/tools/mcp/discovered')

export const adoptServers = (): Promise<{ added: number; found: number }> =>
  _fetch('/api/tools/mcp/adopt', { method: 'POST' })

export const mcpServerAction = (
  name: string,
  action: 'enable' | 'disable' | 'test' | 'remove',
): Promise<{ ok: boolean; error?: string; enabled?: boolean; granted?: boolean; callable?: boolean; tool_count?: number }> =>
  _fetch(`/api/tools/mcp/${encodeURIComponent(name)}/${action}`, { method: 'POST' })

export const getServerTools = (name: string): Promise<{ tools: { name: string; description: string }[] }> =>
  _fetch(`/api/tools/mcp/${encodeURIComponent(name)}/tools`)

export const getSkills = (): Promise<{ skills: SkillRow[]; targets: string[] }> =>
  _fetch('/api/tools/skills')

export const saveSkillApi = (body: { name: string; description: string; body: string }): Promise<{ ok: boolean }> =>
  _fetch('/api/tools/skills', { method: 'POST', body: JSON.stringify(body) })

export const deleteSkill = (name: string): Promise<{ ok: boolean }> =>
  _fetch(`/api/tools/skills/${encodeURIComponent(name)}`, { method: 'DELETE' })

export const syncSkills = (): Promise<{ written: string[]; skipped: string[]; conflicts: string[]; targets: string[] }> =>
  _fetch('/api/tools/skills/sync', { method: 'POST' })

export const importSkills = (dryRun = true): Promise<{ imported: string[]; skipped: string[]; conflicts: string[]; dry_run: boolean; found: number }> =>
  _fetch(`/api/tools/skills/import?dry_run=${dryRun}`, { method: 'POST' })

export const getGeneratedTools = (): Promise<{ tools: GeneratedTool[] }> =>
  _fetch('/api/tools/generated')

export const showGeneratedTool = (name: string): Promise<{ ok: boolean; manifest?: Record<string, unknown>; source?: string; error?: string }> =>
  _fetch(`/api/tools/generated/${encodeURIComponent(name)}`)

export const generateTool = (description: string, cloud = false): Promise<{ ok: boolean; name?: string; capabilities?: string[]; error?: string; kind?: string }> =>
  _fetch('/api/tools/generated', { method: 'POST', body: JSON.stringify({ description, cloud }) })

export const generatedToolAction = (
  name: string,
  action: 'enable' | 'disable' | 'test' | 'remove',
): Promise<{ ok: boolean; enabled?: boolean; output?: string; error?: string }> =>
  _fetch(`/api/tools/generated/${encodeURIComponent(name)}/${action}`, { method: 'POST' })


// ── Chat attachments ─────────────────────────────────────────────────────────

export interface AttachmentMeta {
  ok: boolean
  id?: string
  name?: string
  format?: string
  chars?: number
  truncated?: boolean
  warnings?: string[]
  error?: string
}

export async function uploadAttachment(file: File): Promise<AttachmentMeta> {
  const form = new FormData()
  form.append('file', file)
  // No Content-Type header: the browser must set the multipart boundary.
  const res = await fetch('/api/chat/attach', { method: 'POST', body: form })
  if (!res.ok) return { ok: false, error: `${res.status} ${res.statusText}` }
  return res.json() as Promise<AttachmentMeta>
}

export const removeAttachment = (id: string): Promise<{ ok: boolean }> =>
  _fetch(`/api/chat/attach/${encodeURIComponent(id)}`, { method: 'DELETE' })
