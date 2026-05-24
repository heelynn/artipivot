export interface SSEEvent {
  type: 'token' | 'node' | 'done' | 'error'
  content?: string
  name?: string
  data?: unknown
  thread_id?: string
  message?: string
}

export interface SSEOptions {
  agentId: string
  message: string
  threadId?: string
  userId?: string
  onToken: (content: string) => void
  onNode?: (name: string, data: unknown) => void
  onDone?: (threadId: string) => void
  onError?: (message: string) => void
}

export async function streamChat(options: SSEOptions): Promise<void> {
  const { agentId, message, threadId = 'default', userId = 'anonymous', onToken, onNode, onDone, onError } = options

  const res = await fetch(`/api/v1/chat/${agentId}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
    body: JSON.stringify({ message, thread_id: threadId, user_id: userId }),
  })

  if (!res.ok) {
    const body = await res.text()
    onError?.(`API ${res.status}: ${body}`)
    return
  }

  if (!res.body) {
    onError?.('No response body')
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('data: ')) continue

        const jsonStr = trimmed.slice(6)
        if (!jsonStr) continue

        try {
          const event: SSEEvent = JSON.parse(jsonStr)

          switch (event.type) {
            case 'token':
              onToken(event.content ?? '')
              break
            case 'node':
              onNode?.(event.name ?? '', event.data)
              break
            case 'done':
              onDone?.(event.thread_id ?? '')
              break
            case 'error':
              onError?.(event.message ?? 'Unknown error')
              break
          }
        } catch {
          // Skip malformed JSON lines
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
