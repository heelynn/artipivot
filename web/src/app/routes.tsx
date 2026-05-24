import { Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from './layout'
import { ChatPage } from '@/features/chat/ChatPage'
import { AgentsPage } from '@/features/agents/AgentsPage'
import { ConfigPage } from '@/features/config/ConfigPage'
import { ObservePage } from '@/features/observe/ObservePage'
import { RuntimePage } from '@/features/runtime/RuntimePage'

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<ChatPage />} />
        <Route path="admin/agents" element={<AgentsPage />} />
        <Route path="admin/config" element={<ConfigPage />} />
        <Route path="admin/observe" element={<ObservePage />} />
        <Route path="admin/runtime" element={<RuntimePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
