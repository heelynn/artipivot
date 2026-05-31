const API_BASE = import.meta.env.PROD ? '' : ''

export interface MemoryConfig {
  l2?: boolean
  l3?: boolean
  embedding?: { enabled?: boolean }
  context_window?: {
    enabled?: boolean
    strategy?: string
    trigger_tokens?: number
    keep_messages?: number
  }
  extraction?: {
    enabled?: boolean
    max_messages?: number
    write_on?: string
  }
  retention?: {
    knowledge_ttl_days?: number | null
    max_items_per_namespace?: number | null
  }
}

export interface AgentInfo {
  agent_id: string
  model?: Record<string, unknown>
  confidence_threshold?: number
  intent_map?: Record<string, string>
  intent_descriptions?: Record<string, string>
  circuit?: { enabled: boolean; failure_threshold: number; recovery_timeout: number }
  sub_agent_refs?: unknown[]
  tools?: string[]
  prompts?: Record<string, string>
  default_responses?: Record<string, string>
  declarative_sub_agents?: Record<string, unknown>
  graph_sub_agents?: Record<string, unknown>
  memory?: MemoryConfig
}

export interface ChatRequest {
  message: string
  thread_id?: string
  user_id?: string
}

export interface ChatResponse {
  response: string
  thread_id: string
}

export interface ToolInfo {
  name: string
  type?: string
  module?: string
  function?: string
  config?: Record<string, unknown>
  status?: string
  description?: string
}

export interface SubAgentInfo {
  name: string
  strategy?: string
  tools?: string[]
  system_prompt?: string
  strategy_config?: Record<string, unknown>
  graph?: Record<string, unknown>
  status?: string
}

export interface ThreadInfo {
  thread_id: string
  last_message: string
  updated_at: string
}

export interface ThreadMessages {
  thread_id: string
  messages: { role: 'user' | 'assistant'; content: string }[]
}

export interface CircuitStatus {
  agent_id: string
  circuit: {
    enabled: boolean
    failure_threshold: number
    recovery_timeout: number
  }
}

export interface ModelConfig {
  provider?: string
  name?: string
  temperature?: number
  timeout?: number
  max_tokens?: number
  base_url?: string
}

export interface RoutingConfig {
  intent_map?: Record<string, string>
  threshold?: number
  default_agent?: string
}

export interface RateLimitConfig {
  scope?: string
  agent_id?: string
  tool_name?: string
  overrides?: Record<string, unknown>
  defaults?: Record<string, unknown>
  agent_overrides?: Record<string, Record<string, unknown>>
  tool_overrides?: Record<string, Record<string, unknown>>
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      ...options?.headers,
    },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API ${res.status}: ${body}`)
  }
  return res.json()
}

export const api = {
  // Chat
  chat(agentId: string, body: ChatRequest) {
    return request<ChatResponse>(`/api/v1/chat/${agentId}`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  // Agents
  async listAgents(): Promise<AgentInfo[]> {
    const data = await request<{ agents: string[] }>('/api/v1/admin/agents')
    const ids = data.agents ?? []
    const details = await Promise.all(
      ids.map(async id => {
        try {
          return await request<AgentInfo>(`/api/v1/admin/agents/${id}`)
        } catch {
          return { agent_id: id } as AgentInfo
        }
      })
    )
    return details
  },
  getAgent(agentId: string) {
    return request<AgentInfo>(`/api/v1/admin/agents/${agentId}`)
  },
  registerAgent(yaml: string) {
    return request<AgentInfo>('/api/v1/admin/agents', {
      method: 'POST',
      body: yaml,
      headers: { 'Content-Type': 'application/yaml', 'Accept': 'application/json' },
    })
  },
  registerAgentJson(data: Record<string, unknown>) {
    return request<AgentInfo>('/api/v1/admin/agents', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },
  updateAgent(agentId: string, data: Record<string, unknown>) {
    return request<{ status: string; agent_id: string; fields: string[] }>(
      `/api/v1/admin/agents/${agentId}`,
      { method: 'PUT', body: JSON.stringify(data) }
    )
  },
  deleteAgent(agentId: string) {
    return request<void>(`/api/v1/admin/agents/${agentId}`, { method: 'DELETE' })
  },
  getCircuitStatus(agentId: string) {
    return request<CircuitStatus>(`/api/v1/admin/agents/${agentId}/circuit`)
  },

  // Models
  getModel(agentId: string) {
    return request<ModelConfig>(`/api/v1/admin/models/${agentId}`)
  },
  setUserModel(userId: string, agentId: string, config: ModelConfig) {
    return request<void>(`/api/v1/admin/models/user/${userId}/agent/${agentId}`, {
      method: 'PUT',
      body: JSON.stringify(config),
    })
  },
  deleteUserModel(userId: string, agentId: string) {
    return request<void>(`/api/v1/admin/models/user/${userId}/agent/${agentId}`, {
      method: 'DELETE',
    })
  },

  // Routing
  getRouting(agentId: string) {
    return request<RoutingConfig>(`/api/v1/admin/routing/${agentId}`)
  },

  // Rate limits
  getRateLimits() {
    return request<RateLimitConfig>('/api/v1/admin/ratelimits')
  },
  updateAgentRateLimit(agentId: string, config: Record<string, unknown>) {
    return request<void>(`/api/v1/admin/ratelimits/agent/${agentId}`, {
      method: 'PUT',
      body: JSON.stringify(config),
    })
  },

  // Tools
  listTools() {
    return request<ToolInfo[]>('/api/v1/admin/tools')
  },
  createTool(yaml: string) {
    return request<ToolInfo>('/api/v1/admin/tools', {
      method: 'POST',
      body: yaml,
      headers: { 'Content-Type': 'application/yaml', 'Accept': 'application/json' },
    })
  },
  deleteTool(name: string) {
    return request<void>(`/api/v1/admin/tools/${name}`, { method: 'DELETE' })
  },
  updateTool(name: string, data: Record<string, unknown>) {
    return request<ToolInfo>('/api/v1/admin/tools', {
      method: 'POST',
      body: JSON.stringify({ name, ...data }),
    })
  },

  // Sub-agents
  listSubAgents() {
    return request<SubAgentInfo[]>('/api/v1/admin/sub-agents')
  },
  createSubAgent(yaml: string) {
    return request<SubAgentInfo>('/api/v1/admin/sub-agents', {
      method: 'POST',
      body: yaml,
      headers: { 'Content-Type': 'application/yaml', 'Accept': 'application/json' },
    })
  },
  deleteSubAgent(name: string) {
    return request<void>(`/api/v1/admin/sub-agents/${name}`, { method: 'DELETE' })
  },
  updateSubAgent(name: string, data: Record<string, unknown>) {
    return request<SubAgentInfo>('/api/v1/admin/sub-agents', {
      method: 'POST',
      body: JSON.stringify({ name, ...data }),
    })
  },

  // Rate limits
  updateToolRateLimit(toolName: string, config: Record<string, unknown>) {
    return request<void>(`/api/v1/admin/ratelimits/tool/${toolName}`, {
      method: 'PUT',
      body: JSON.stringify(config),
    })
  },

  // Runtime observation (read-only)
  listRuntimeTools() {
    return request<ToolInfo[]>('/api/v1/admin/runtime/tools')
  },
  listRuntimeSubAgents() {
    return request<SubAgentInfo[]>('/api/v1/admin/runtime/sub-agents')
  },

  // Graph
  async getGraphMermaid(agentId: string) {
    const data = await request<{ agent_id: string; graphs: Record<string, string> }>(`/api/v1/admin/graph/${agentId}/mermaid`)
    // Join multiple graph diagrams
    const diagrams = Object.values(data.graphs ?? {}).join('\n')
    return { mermaid: diagrams }
  },
  getGraphStructure(agentId: string) {
    return request<Record<string, unknown>>(`/api/v1/admin/graph/${agentId}/structure`)
  },

  // Health
  health() {
    return request<{ status: string }>('/health')
  },

  // Threads
  listThreads(agentId: string) {
    return request<ThreadInfo[]>(`/api/v1/chat/${agentId}/threads`)
  },
  getThreadMessages(agentId: string, threadId: string) {
    return request<ThreadMessages>(`/api/v1/chat/${agentId}/threads/${threadId}/messages`)
  },
  deleteThread(agentId: string, threadId: string) {
    return request<{ status: string; thread_id: string }>(
      `/api/v1/chat/${agentId}/threads/${threadId}`,
      { method: 'DELETE' }
    )
  },
}
