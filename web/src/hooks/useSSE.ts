import { useState, useCallback, useRef } from 'react'
import { streamChat, type SSEOptions } from '@/lib/sse'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}

export function useSSE() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [nodeStatus, setNodeStatus] = useState<string | null>(null)
  const abortRef = useRef(false)

  const sendMessage = useCallback(
    async (agentId: string, message: string, threadId?: string, userId?: string) => {
      abortRef.current = false

      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: message,
        timestamp: Date.now(),
      }

      const assistantId = crypto.randomUUID()
      const assistantMsg: Message = {
        id: assistantId,
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
      }

      setMessages(prev => [...prev, userMsg, assistantMsg])
      setIsStreaming(true)
      setNodeStatus(null)

      const options: SSEOptions = {
        agentId,
        message,
        threadId,
        userId,
        onToken(content) {
          if (abortRef.current) return
          setMessages(prev =>
            prev.map(m => (m.id === assistantId ? { ...m, content: m.content + content } : m))
          )
        },
        onNode(name) {
          setNodeStatus(name)
        },
        onDone() {
          setIsStreaming(false)
          setNodeStatus(null)
        },
        onError(errorMsg) {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId
                ? { ...m, content: m.content || `[Error] ${errorMsg}` }
                : m
            )
          )
          setIsStreaming(false)
          setNodeStatus(null)
        },
      }

      await streamChat(options)
    },
    []
  )

  const stopStreaming = useCallback(() => {
    abortRef.current = true
    setIsStreaming(false)
    setNodeStatus(null)
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    setNodeStatus(null)
  }, [])

  return { messages, isStreaming, nodeStatus, sendMessage, stopStreaming, clearMessages }
}
