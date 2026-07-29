import { NavBar, ThemeToggle } from '../ds'

const APP_LINKS = [
  { label: 'dashboard', to: '/dashboard' },
  { label: 'chat', to: '/chat' },
  { label: 'memory', to: '/memory' },
  { label: 'notes', to: '/notes' },
  { label: 'wiki', to: '/wiki' },
  { label: 'activity', to: '/observability' },
  { label: 'tools', to: '/tools' },
  { label: 'agents', to: '/agents' },
  { label: 'settings', to: '/settings' },
]

export default function AppNav() {
  return <NavBar links={APP_LINKS} showStatus right={<ThemeToggle />} />
}
