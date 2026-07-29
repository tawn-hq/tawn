import { Routes, Route, Navigate } from 'react-router-dom'
import Home from './pages/Home'
import Dashboard from './pages/Dashboard'
import Chat from './pages/Chat'
import Memory from './pages/Memory'
import Notes from './pages/Notes'
import Observability from './pages/Observability'
import Wiki from './pages/Wiki'
import Tools from './pages/Tools'
import Shell from './components/Shell'
import { ErrorProvider } from './components/Errors'
import Agents from './pages/Agents'
import Settings from './pages/Settings'
import Setup from './pages/Setup'
import DomainCreate from './pages/DomainCreate'
import DomainPage from './pages/DomainPage'
import Logs from './pages/Logs'
import MemoryDetail from './pages/MemoryDetail'
import AgentConversation from './pages/AgentConversation'

export default function App() {
  return (
    <ErrorProvider>
    <Shell>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/chat" element={<Chat />} />
      <Route path="/memory" element={<Memory />} />
      <Route path="/notes" element={<Notes />} />
      <Route path="/observability" element={<Observability />} />
      <Route path="/wiki" element={<Wiki />} />
      <Route path="/tools" element={<Tools />} />
      <Route path="/agents" element={<Agents />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="/setup" element={<Setup />} />
      <Route path="/domain/create" element={<DomainCreate />} />
      <Route path="/domain/:name" element={<DomainPage />} />
      <Route path="/memory/chunk/:id" element={<MemoryDetail />} />
      <Route path="/agents/conversation/:id" element={<AgentConversation />} />
      <Route path="/audit" element={<Navigate to="/settings" replace />} />
      <Route path="/logs" element={<Logs />} />
      <Route path="/grants" element={<Navigate to="/settings" replace />} />
      <Route path="/profile" element={<Navigate to="/settings" replace />} />
      <Route path="/history" element={<Navigate to="/chat" replace />} />
      <Route path="/models" element={<Navigate to="/settings" replace />} />
    </Routes>
    </Shell>
    </ErrorProvider>
  )
}
