import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Badge, Button } from '../ds'
import { getChunk, type FeedChunk } from '../lib/api'
import { marked } from 'marked'

marked.setOptions({ breaks: true })

const DOMAINS = ['work', 'wealth', 'research', 'academic', 'hobby'] as const
type Domain = typeof DOMAINS[number]

function ContentBody({ content }: { content: string }) {
  return (
    <div
      className="tawn-md"
      style={{ fontSize: 15, lineHeight: 1.75, color: 'var(--tawn-text)' }}
      dangerouslySetInnerHTML={{ __html: marked.parse(content) as string }}
    />
  )
}

export default function MemoryDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [chunk, setChunk] = useState<FeedChunk | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!id) return
    getChunk(Number(id))
      .then(setChunk)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
  }, [id])

  const dom = chunk && DOMAINS.includes(chunk.domain as Domain) ? chunk.domain as Domain : undefined

  return (
    <>
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '32px 24px 80px' }}>
        <div style={{ marginBottom: 20 }}>
          <Button variant="secondary" size="sm" onClick={() => navigate(-1)}>← back</Button>
        </div>

        {error && (
          <p style={{ color: 'var(--tawn-crit)', fontSize: 14 }}>error: {error}</p>
        )}

        {chunk && (
          <>
            {/* meta bar */}
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
              {dom && <Badge domain={dom}>{dom}</Badge>}
              {chunk.stale && <Badge status="warn">stale</Badge>}
              <span style={{ fontSize: 10, fontFamily: 'var(--tawn-font-mono)', border: '1px solid var(--tawn-line)', borderRadius: 999, padding: '2px 7px', color: 'var(--tawn-text-3)' }}>
                {chunk.source_type}
              </span>
              <span style={{ fontSize: 11, color: 'var(--tawn-text-3)', fontFamily: 'var(--tawn-font-mono)' }}>
                chunk #{chunk.id}
              </span>
            </div>

            {/* source info */}
            <div style={{ background: 'var(--tawn-raised)', borderRadius: 'var(--tawn-radius-sm)', padding: '10px 14px', marginBottom: 20, fontSize: 12, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-2)', wordBreak: 'break-all' }}>
              <div style={{ marginBottom: 4 }}>
                <span style={{ color: 'var(--tawn-text-3)' }}>source </span>
                <span>{chunk.source_label}</span>
              </div>
              <div style={{ marginBottom: 4, color: 'var(--tawn-text-3)', fontSize: 11 }}>{chunk.source_path}</div>
              <div style={{ display: 'flex', gap: 20, color: 'var(--tawn-text-3)', fontSize: 11 }}>
                {chunk.asof && <span>as of {new Date(chunk.asof).toLocaleString()}</span>}
                {chunk.compiled_at && <span>compiled {new Date(chunk.compiled_at).toLocaleString()}</span>}
              </div>
            </div>

            {/* full content */}
            <div style={{ background: 'var(--tawn-surface)', border: '1px solid var(--tawn-line)', borderRadius: 'var(--tawn-radius)', padding: '24px 28px' }}>
              <ContentBody content={chunk.content} />
            </div>

            {/* footer */}
            <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
              <Button variant="secondary" size="sm" onClick={() => navigate(-1)}>← back to memory</Button>
            </div>
          </>
        )}

        {!chunk && !error && (
          <p style={{ fontSize: 13, color: 'var(--tawn-text-2)' }}>loading…</p>
        )}
      </div>
    </>
  )
}
