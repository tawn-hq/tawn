import { Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import Chat from './pages/Chat'
import Setup from './pages/Setup'
import GrantsPage from './pages/Grants'
import DomainCreate from './pages/DomainCreate'
import DomainPage from './pages/DomainPage'
import Profile from './pages/Profile'
import Audit from './pages/Audit'
import History from './pages/History'
import Models from './pages/Models'
import Memory from './pages/Memory'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/chat" element={<Chat />} />
      <Route path="/setup" element={<Setup />} />
      <Route path="/grants" element={<GrantsPage />} />
      <Route path="/domain/create" element={<DomainCreate />} />
      <Route path="/domain/:name" element={<DomainPage />} />
      <Route path="/profile" element={<Profile />} />
      <Route path="/audit" element={<Audit />} />
      <Route path="/history" element={<History />} />
      <Route path="/models" element={<Models />} />
      <Route path="/memory" element={<Memory />} />
    </Routes>
  )
}
