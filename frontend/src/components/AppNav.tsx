import { NavBar } from '../ds'

const APP_LINKS = [
  { label: 'dashboard', to: '/dashboard' },
  { label: 'chat', to: '/chat' },
  { label: 'memory', to: '/memory' },
  { label: 'agents', to: '/agents' },
  { label: 'settings', to: '/settings' },
]

export default function AppNav() {
  return <NavBar links={APP_LINKS} showStatus />
}
