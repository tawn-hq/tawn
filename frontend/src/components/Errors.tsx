import { createContext, useCallback, useContext, useEffect, useState } from 'react'

/**
 * Somewhere for failures to go.
 *
 * Pages used to call `.catch(() => {})` on every request — 45 of them. When the
 * backend was down the UI rendered its empty state instead, so "your database
 * is unreachable" and "you have not written any skills yet" looked identical.
 * A user cannot act on a problem they cannot see.
 *
 * `useLoader` replaces that idiom: it keeps the empty state for genuinely empty
 * data, and surfaces an error when the request actually failed.
 */

export interface AppError {
  id: number
  message: string
  detail?: string
}

interface ErrorBus {
  report: (message: string, detail?: string) => void
}

const Ctx = createContext<ErrorBus>({ report: () => {} })

export const useErrors = () => useContext(Ctx)

function messageFor(err: unknown): { message: string; detail?: string } {
  const raw = err instanceof Error ? err.message : String(err)

  // The API client throws `${status} ${body}`; turn the common ones into
  // something that says what to do rather than what went wrong.
  if (/^5\d\d/.test(raw)) {
    return {
      message: 'Tawn hit an internal error.',
      detail: `${raw}\n\nIf this persists, run \`tawn doctor\` — it checks the database, grants and running processes.`,
    }
  }
  if (raw.startsWith('404')) {
    return { message: 'That endpoint is missing.', detail: `${raw}\n\nUsually means the running server is older than the installed code: \`tawn web stop && tawn web start\`.` }
  }
  if (/Failed to fetch|NetworkError|load failed/i.test(raw)) {
    return {
      message: 'Cannot reach Tawn.',
      detail: 'The server is not responding. Start it with `tawn web start`.',
    }
  }
  return { message: 'Something went wrong.', detail: raw }
}

function Toast({ error, onDismiss }: { error: AppError; onDismiss: () => void }) {
  const [open, setOpen] = useState(false)
  return (
    <div
      style={{
        border: '1px solid var(--tawn-crit)',
        borderRadius: 'var(--tawn-radius-sm)',
        background: 'var(--tawn-surface)',
        boxShadow: '0 8px 28px rgba(0,0,0,0.24)',
        padding: '11px 13px',
        maxWidth: 380,
        pointerEvents: 'auto',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--tawn-crit)' }}>
          {error.message}
        </span>
        <button
          onClick={onDismiss}
          aria-label="dismiss"
          style={{ marginLeft: 'auto', border: 'none', background: 'none', color: 'var(--tawn-text-3)', cursor: 'pointer', fontSize: 14, lineHeight: 1 }}
        >
          ✕
        </button>
      </div>
      {error.detail && (
        <>
          <button
            onClick={() => setOpen(!open)}
            style={{ marginTop: 5, border: 'none', background: 'none', padding: 0, color: 'var(--tawn-text-3)', cursor: 'pointer', fontSize: 11.5, fontFamily: 'var(--tawn-font-mono)' }}
          >
            {open ? 'hide details' : 'details'}
          </button>
          {open && (
            <pre style={{ marginTop: 6, marginBottom: 0, fontSize: 11.5, fontFamily: 'var(--tawn-font-mono)', color: 'var(--tawn-text-2)', whiteSpace: 'pre-wrap', maxHeight: 180, overflowY: 'auto' }}>
              {error.detail}
            </pre>
          )}
        </>
      )}
    </div>
  )
}

export function ErrorProvider({ children }: { children: React.ReactNode }) {
  const [errors, setErrors] = useState<AppError[]>([])

  const report = useCallback((message: string, detail?: string) => {
    setErrors((prev) => {
      // Identical failures repeat on every poll; showing one is enough.
      if (prev.some((e) => e.message === message && e.detail === detail)) return prev
      return [...prev, { id: Date.now() + Math.random(), message, detail }]
    })
  }, [])

  return (
    <Ctx.Provider value={{ report }}>
      {children}
      <div
        style={{
          position: 'fixed', right: 16, bottom: 16, zIndex: 200,
          display: 'flex', flexDirection: 'column', gap: 8,
          pointerEvents: 'none',
        }}
      >
        {errors.slice(-3).map((e) => (
          <Toast
            key={e.id}
            error={e}
            onDismiss={() => setErrors((prev) => prev.filter((x) => x.id !== e.id))}
          />
        ))}
      </div>
    </Ctx.Provider>
  )
}

/**
 * Load data, and say so when it fails.
 *
 * Returns `loading` so a page can tell "not fetched yet" from "fetched, and
 * there is nothing" — the distinction the old `.catch(() => {})` destroyed.
 */
export function useLoader<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  initial: T | null = null,
) {
  const { report } = useErrors()
  const [data, setData] = useState<T | null>(initial)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  const reload = useCallback(() => {
    setLoading(true)
    return fetcher()
      .then((d) => { setData(d); setFailed(false) })
      .catch((err: unknown) => {
        setFailed(true)
        const { message, detail } = messageFor(err)
        report(message, detail)
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => { reload() }, [reload])

  return { data, loading, failed, reload, setData }
}

/**
 * For one-off actions (save, delete, run) rather than loads.
 */
export function useAction() {
  const { report } = useErrors()
  const [busy, setBusy] = useState(false)

  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | null> => {
    setBusy(true)
    try {
      return await fn()
    } catch (err: unknown) {
      const { message, detail } = messageFor(err)
      report(message, detail)
      return null
    } finally {
      setBusy(false)
    }
  }, [report])

  return { run, busy }
}
