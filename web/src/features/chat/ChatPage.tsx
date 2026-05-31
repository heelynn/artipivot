import { useState, useRef, useEffect, useCallback } from 'react'
import { useSSE, type Message } from '@/hooks/useSSE'
import { api, type AgentInfo, type ThreadInfo } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'
import { Send, Bot, User, Loader2, Plus, MessageSquare, Trash2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'

export function ChatPage() {
  const { messages, isStreaming, nodeStatus, sendMessage, clearMessages, loadMessages } = useSSE()
  const [input, setInput] = useState('')
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [selectedAgent, setSelectedAgent] = useState<string>('')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const { t } = useTranslation()
  const [threadId, setThreadId] = useState<string>(() => crypto.randomUUID())
  const [threads, setThreads] = useState<ThreadInfo[]>([])
  const [loadingThreads, setLoadingThreads] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    api.listAgents().then(setAgents).catch(console.error)
  }, [])

  useEffect(() => {
    if (agents.length > 0 && !selectedAgent) {
      setSelectedAgent(agents[0].agent_id)
    }
  }, [agents, selectedAgent])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const refreshThreads = useCallback(async (agentId: string) => {
    setLoadingThreads(true)
    try {
      const list = await api.listThreads(agentId)
      setThreads(list)
    } catch {
      setThreads([])
    } finally {
      setLoadingThreads(false)
    }
  }, [])

  // Load threads when agent changes
  useEffect(() => {
    if (selectedAgent) {
      refreshThreads(selectedAgent)
      // Start a new thread when switching agents
      setThreadId(crypto.randomUUID())
      clearMessages()
    }
  }, [selectedAgent]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleNewThread = () => {
    setThreadId(crypto.randomUUID())
    clearMessages()
  }

  const handleSelectThread = async (thread: ThreadInfo) => {
    if (thread.thread_id === threadId) return
    setThreadId(thread.thread_id)
    try {
      const data = await api.getThreadMessages(selectedAgent, thread.thread_id)
      const loaded: Message[] = data.messages.map((m, i) => ({
        id: `hist-${thread.thread_id}-${i}`,
        role: m.role,
        content: m.content,
        timestamp: 0,
      }))
      loadMessages(loaded)
    } catch {
      clearMessages()
    }
  }

  const handleDeleteThread = async (e: React.MouseEvent, thread: ThreadInfo) => {
    e.stopPropagation()
    try {
      await api.deleteThread(selectedAgent, thread.thread_id)
      setThreads(prev => prev.filter(t => t.thread_id !== thread.thread_id))
      if (thread.thread_id === threadId) {
        handleNewThread()
      }
    } catch (err) {
      console.error('Failed to delete thread', err)
    }
  }

  const handleSelectAgent = (agentId: string) => {
    if (agentId !== selectedAgent) {
      setSelectedAgent(agentId)
    }
  }

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed || !selectedAgent || isStreaming) return
    setInput('')
    sendMessage(selectedAgent, trimmed, threadId)
    // Refresh thread list after sending
    setTimeout(() => refreshThreads(selectedAgent), 1000)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex h-full">
      {/* Agent sidebar */}
      <div
        className={cn(
          'flex flex-col border-r border-border bg-muted/30 transition-all duration-200',
          sidebarOpen ? 'w-56' : 'w-0 overflow-hidden'
        )}
      >
        <div className="flex items-center justify-between border-b border-border p-3">
          <span className="text-sm font-medium">{t('chat.agentsSidebar')}</span>
          <button
            onClick={() => setSidebarOpen(false)}
            className="rounded p-1 text-muted-foreground hover:bg-accent"
          >
            <PanelLeftClose />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {/* Agent list */}
          <div className="p-2 space-y-1">
            {agents.map(agent => (
              <button
                key={agent.agent_id}
                onClick={() => handleSelectAgent(agent.agent_id)}
                className={cn(
                  'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-left transition-colors',
                  selectedAgent === agent.agent_id
                    ? 'bg-accent text-accent-foreground font-medium'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                )}
              >
                <Bot size={16} />
                <div className="truncate flex-1">
                  <div className="text-sm">{agent.agent_id}</div>
                  {typeof agent.model === 'object' && agent.model && 'name' in agent.model && (
                    <div className="text-xs text-muted-foreground truncate">{String(agent.model.name)}</div>
                  )}
                </div>
              </button>
            ))}
          </div>

          {/* Thread list for selected agent */}
          {selectedAgent && (
            <>
              <div className="flex items-center justify-between border-t border-border px-3 py-2">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {t('chat.sessions', 'Sessions')}
                </span>
                <button
                  onClick={handleNewThread}
                  className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  title={t('chat.newSession', 'New session')}
                >
                  <Plus size={14} />
                </button>
              </div>
              <div className="px-2 pb-2 space-y-0.5">
                {loadingThreads ? (
                  <div className="flex items-center justify-center py-3">
                    <Loader2 size={14} className="animate-spin text-muted-foreground" />
                  </div>
                ) : threads.length === 0 ? (
                  <div className="px-2 py-3 text-xs text-muted-foreground text-center">
                    {t('chat.noSessions', 'No sessions yet')}
                  </div>
                ) : (
                  threads.map(thread => (
                    <div
                      key={thread.thread_id}
                      onClick={() => handleSelectThread(thread)}
                      className={cn(
                        'group flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs cursor-pointer transition-colors',
                        thread.thread_id === threadId
                          ? 'bg-accent text-accent-foreground'
                          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                      )}
                    >
                      <MessageSquare size={12} className="shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="truncate">{thread.last_message || thread.thread_id.slice(0, 8)}</div>
                        {thread.updated_at && (
                          <div className="text-[10px] opacity-60 truncate">{formatTime(thread.updated_at)}</div>
                        )}
                      </div>
                      <button
                        onClick={e => handleDeleteThread(e, thread)}
                        className="shrink-0 rounded p-0.5 opacity-0 group-hover:opacity-100 hover:bg-destructive/20 hover:text-destructive transition-opacity"
                        title={t('chat.deleteSession', 'Delete session')}
                      >
                        <Trash2 size={10} />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Toggle sidebar when closed */}
      {!sidebarOpen && (
        <div className="flex items-center border-r border-border px-2">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded p-1 text-muted-foreground hover:bg-accent"
          >
            <PanelLeft />
          </button>
        </div>
      )}

      {/* Chat area */}
      <div className="flex flex-1 flex-col">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <div className="text-center text-muted-foreground">
                <Bot size={48} className="mx-auto mb-4 opacity-20" />
                <h2 className="text-xl font-medium">{t('chat.title')}</h2>
                <p className="mt-1 text-sm">{t('chat.subtitle')}</p>
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-4 p-4 pb-0">
              {messages.map(msg => (
                <MessageBubble key={msg.id} message={msg} isStreaming={isStreaming} />
              ))}

              {isStreaming && nodeStatus && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 size={14} className="animate-spin" />
                  <span>{t('chat.processing', { status: nodeStatus })}</span>
                </div>
              )}

              <div ref={messagesEndRef} className="h-4" />
            </div>
          )}
        </div>

        {/* Input area */}
        <div className="border-t border-border bg-background p-4">
          <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border border-border bg-muted/30 p-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                selectedAgent ? t('chat.placeholder', { agent: selectedAgent }) : t('chat.placeholderNoAgent')
              }
              disabled={!selectedAgent || isStreaming}
              rows={1}
              className="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted-foreground/50 disabled:opacity-50"
              style={{ maxHeight: '120px' }}
              onInput={e => {
                const el = e.target as HTMLTextAreaElement
                el.style.height = 'auto'
                el.style.height = Math.min(el.scrollHeight, 120) + 'px'
              }}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || !selectedAgent || isStreaming}
              className="rounded-lg bg-primary p-2 text-primary-foreground hover:bg-primary/90 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function MessageBubble({ message, isStreaming }: { message: Message; isStreaming: boolean }) {
  const isUser = message.role === 'user'

  return (
    <div className={cn('flex gap-3', isUser ? 'flex-row-reverse' : '')}>
      <div
        className={cn(
          'flex h-7 w-7 shrink-0 items-center justify-center rounded-full',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
        )}
      >
        {isUser ? <User size={14} /> : <Bot size={14} />}
      </div>
      <div
        className={cn(
          'max-w-[80%] rounded-2xl px-4 py-2.5 text-sm',
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted text-foreground'
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
              {message.content}
            </ReactMarkdown>
            {isStreaming && message.content && (
              <span className="inline-block w-1.5 h-4 ml-0.5 bg-foreground/70 animate-pulse" />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function formatTime(isoStr: string): string {
  try {
    const d = new Date(isoStr)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMin = Math.floor(diffMs / 60000)

    if (diffMin < 1) return 'just now'
    if (diffMin < 60) return `${diffMin}m ago`

    const diffHr = Math.floor(diffMin / 60)
    if (diffHr < 24) return `${diffHr}h ago`

    return d.toLocaleDateString()
  } catch {
    return ''
  }
}

function PanelLeftClose(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <rect width="18" height="18" x="3" y="3" rx="2" /><path d="M9 3v18" /><path d="m16 15-3-3 3-3" />
    </svg>
  )
}

function PanelLeft(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <rect width="18" height="18" x="3" y="3" rx="2" /><path d="M9 3v18" /><path d="m14 9 3 3-3 3" />
    </svg>
  )
}
