import { useEffect, useMemo, useState } from 'react'
import { marked } from 'marked'
import EntityGraph from '../components/EntityGraph'
import { Card, Input, Badge, Button } from '../ds'
import { useErrors } from '../components/Errors'
import {
  getWikiTree, getWikiPage, getWikiEntity, getWikiGraph,
  type WikiTree, type WikiEntity, type GraphData,
} from '../lib/api'

const DOMAINS = ['work', 'wealth', 'research', 'academic', 'hobby'] as const
type Domain = typeof DOMAINS[number]

const EMPTY_GRAPH: GraphData = { nodes: [], links: [] }

/**
 * Rewrite [[Name]] into a clickable span before marked runs.
 *
 * The files keep Obsidian's wikilink syntax so the vault stays navigable;
 * resolving them to internal navigation is purely a viewer concern.
 */
function renderWikiMarkdown(src: string): string {
  const linked = src.replace(
    /\[\[([^\]]+)\]\]/g,
    (_m, name: string) =>
      `<a href="#" data-wikilink="${name.replace(/"/g, '&quot;')}">${name}</a>`,
  )
  return marked.parse(linked) as string
}

export default function Wiki() {
  const { report } = useErrors()
  const reportError = (e: unknown) => report(e instanceof Error ? e.message : String(e))
  const [tree, setTree] = useState<WikiTree | null>(null)
  const [filter, setFilter] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [entity, setEntity] = useState<WikiEntity | null>(null)
  const [page, setPage] = useState('')
  const [graph, setGraph] = useState<GraphData>(EMPTY_GRAPH)
  const [rootGraph, setRootGraph] = useState<GraphData>(EMPTY_GRAPH)
  const [error, setError] = useState('')

  useEffect(() => {
    getWikiTree().then(setTree).catch(() => setTree(null))
    getWikiGraph({ cluster: true }).then(setRootGraph).catch(reportError)
  }, [])

  useEffect(() => {
    if (!selected) {
      setEntity(null)
      setPage('')
      setGraph(EMPTY_GRAPH)
      return
    }
    setError('')
    getWikiEntity(selected)
      .then((e) => {
        setEntity(e)
        return getWikiGraph({ entity: e.canonical, depth: 1 })
      })
      .then((g) => g && setGraph(g))
      .catch(() => {
        setEntity(null)
        setError(`no entity page for "${selected}" yet — run tawn enrich`)
      })
    getWikiPage(`entities/${selected}.md`)
      .then((p) => setPage(p.content))
      .catch(() => setPage(''))
  }, [selected])

  const entities = useMemo(() => {
    const all = tree?.entities ?? []
    if (!filter.trim()) return all.slice(0, 200)
    const q = filter.toLowerCase()
    return all.filter((e) => e.name.toLowerCase().includes(q)).slice(0, 200)
  }, [tree, filter])

  const html = useMemo(() => (page ? renderWikiMarkdown(page) : ''), [page])

  // Wikilinks are rendered from markdown, so they cannot carry React
  // handlers — delegate from the container instead.
  function onBodyClick(e: React.MouseEvent<HTMLDivElement>) {
    const target = (e.target as HTMLElement).closest('[data-wikilink]')
    if (target) {
      e.preventDefault()
      setSelected(target.getAttribute('data-wikilink'))
    }
  }

  return (
    <>
      <div style={{ maxWidth: 1040, margin: '0 auto', padding: '32px 24px 64px' }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>wiki</h1>
        <p style={{ fontSize: 13, color: 'var(--tawn-text-2)', marginBottom: 20 }}>
          what your twin has worked out — entities, how they connect, and where each came from.
        </p>

        {tree && !tree.ready && (
          <Card style={{ marginBottom: 16 }}>
            <p style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>
              Nothing compiled yet. Run <code>tawn compile</code>, then <code>tawn enrich</code>.
            </p>
          </Card>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(160px, 220px) 1fr', gap: 16, alignItems: 'start' }}>
          <Card padded={false}>
            <div style={{ padding: 10, borderBottom: '1px solid var(--tawn-line)' }}>
              <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="filter entities…" />
            </div>
            <div style={{ maxHeight: 460, overflowY: 'auto' }}>
              {entities.map((e) => (
                <div
                  key={e.name}
                  onClick={() => setSelected(e.name)}
                  style={{
                    padding: '7px 11px',
                    fontSize: 12,
                    cursor: 'pointer',
                    borderBottom: '1px solid var(--tawn-line)',
                    background: selected === e.name ? 'var(--tawn-lapis-soft)' : 'transparent',
                    color: selected === e.name ? 'var(--tawn-text)' : 'var(--tawn-text-2)',
                    fontWeight: selected === e.name ? 600 : 400,
                  }}
                >
                  {e.name}
                </div>
              ))}
              {entities.length === 0 && (
                <div style={{ padding: 14, fontSize: 12, color: 'var(--tawn-text-3)' }}>
                  no entities yet
                </div>
              )}
            </div>
          </Card>

          <Card padded={false}>
            {selected && entity ? (
              <>
                <div style={{ borderBottom: '1px solid var(--tawn-line)' }}>
                  <EntityGraph data={graph} height={230} onSelect={setSelected} />
                </div>
                <div style={{ padding: 16 }} onClick={onBodyClick}>
                  {DOMAINS.includes(entity.domain as Domain) && (
                    <Badge domain={entity.domain as Domain}>{entity.domain}</Badge>
                  )}
                  <h2 style={{ fontSize: 17, fontWeight: 700, margin: '7px 0 3px' }}>{entity.canonical}</h2>
                  <div style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-3)', marginBottom: 12 }}>
                    {entity.related.length} links · {entity.backlinks.length} backlinks
                  </div>

                  {html ? (
                    <div
                      className="tawn-md"
                      dangerouslySetInnerHTML={{ __html: html }}
                      style={{ fontSize: 13.5, lineHeight: 1.65, color: 'var(--tawn-text)' }}
                    />
                  ) : (
                    <p style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>
                      No page written yet — run <code>tawn compile</code>.
                    </p>
                  )}

                  {entity.backlinks.length > 0 && (
                    <>
                      <div style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--tawn-text-3)', margin: '16px 0 6px' }}>
                        linked from
                      </div>
                      {entity.backlinks.map((b) => (
                        <div
                          key={`${b.id}-${b.relation}`}
                          onClick={() => setSelected(b.label)}
                          style={{ fontSize: 12.5, color: 'var(--tawn-lapis)', cursor: 'pointer', padding: '3px 0' }}
                        >
                          {b.label} <span style={{ color: 'var(--tawn-text-3)' }}>({b.relation})</span>
                        </div>
                      ))}
                    </>
                  )}

                  <div style={{ marginTop: 18 }}>
                    <Button variant="secondary" size="sm" onClick={() => setSelected(null)}>
                      ← all domains
                    </Button>
                  </div>
                </div>
              </>
            ) : (
              <div style={{ padding: 14 }}>
                <div style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--tawn-text-3)', marginBottom: 8 }}>
                  all domains
                </div>
                <EntityGraph data={rootGraph} height={380} onSelect={setSelected} />
                {rootGraph.clusters && rootGraph.clusters.length > 0 && (
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 10 }}>
                    {rootGraph.clusters.map((c) => (
                      <span key={c.domain} style={{ fontSize: 11, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-2)' }}>
                        {c.domain}: {c.count}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
            {error && (
              <div style={{ padding: 14, fontSize: 12, color: 'var(--tawn-warn)' }}>{error}</div>
            )}
          </Card>
        </div>
      </div>
    </>
  )
}
