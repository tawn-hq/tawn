import { ReactNode } from 'react'

interface TableProps {
  columns: string[]
  rows: ReactNode[][]
}

export function Table({ columns, rows }: TableProps) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr>
            {columns.map((c, i) => (
              <th key={i} style={{ textAlign: 'left', padding: '6px 10px', borderBottom: '1px solid var(--tawn-line)', color: 'var(--tawn-text-2)', fontWeight: 500, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td key={ci} style={{ padding: '8px 10px', borderBottom: '1px solid var(--tawn-line)', color: 'var(--tawn-text)' }}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
