import { ReactNode } from 'react'
import AppNav from './AppNav'

interface Props {
  children: ReactNode
  narrow?: boolean
}

export default function Layout({ children, narrow = false }: Props) {
  return (
    <div style={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column', background: 'var(--tawn-bg)' }}>
      <AppNav />
      <main
        style={{
          flex: 1,
          maxWidth: narrow ? 680 : 900,
          width: '100%',
          margin: '0 auto',
          padding: '32px 20px',
        }}
      >
        {children}
      </main>
    </div>
  )
}
