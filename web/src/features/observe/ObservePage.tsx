import { useState, useEffect, useRef } from 'react'
import { api, type CircuitStatus } from '@/lib/api'
import type { AgentInfo } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Activity, Zap } from 'lucide-react'

export function ObservePage() {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [circuits, setCircuits] = useState<Record<string, CircuitStatus>>({})
  const [selectedAgent, setSelectedAgent] = useState<string>('')
  const [mermaidCode, setMermaidCode] = useState<string>('')
  const mermaidRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.listAgents().then(list => {
      setAgents(list)
      if (list.length > 0) setSelectedAgent(list[0].agent_id)
    })
  }, [])

  useEffect(() => {
    if (agents.length === 0) return
    Promise.all(
      agents.map(async a => {
        try {
          return [a.agent_id, await api.getCircuitStatus(a.agent_id)] as const
        } catch {
          return [a.agent_id, null] as const
        }
      })
    ).then(results => {
      const map: Record<string, CircuitStatus> = {}
      results.forEach(([id, status]) => {
        if (status) map[id] = status
      })
      setCircuits(map)
    })
  }, [agents])

  useEffect(() => {
    if (!selectedAgent) return
    api.getGraphMermaid(selectedAgent)
      .then(data => setMermaidCode(data.mermaid || ''))
      .catch(() => setMermaidCode(''))
  }, [selectedAgent])

  useEffect(() => {
    if (!mermaidCode || !mermaidRef.current) return
    let cancelled = false
    import('mermaid').then(mermaid => {
      if (cancelled) return
      mermaid.default.initialize({ startOnLoad: false, theme: 'dark' })
      mermaid.default.render('graph-svg', mermaidCode).then(({ svg }) => {
        if (!cancelled && mermaidRef.current) {
          mermaidRef.current.innerHTML = svg
        }
      }).catch(console.error)
    })
    return () => { cancelled = true }
  }, [mermaidCode])

  const stateColor = (enabled: boolean) => {
    return enabled
      ? 'bg-green-500/15 text-green-600 border-green-500/30'
      : 'bg-muted text-muted-foreground border-border'
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl">
        <h1 className="text-2xl font-semibold mb-1">Observability</h1>
        <p className="text-sm text-muted-foreground mb-6">
          Circuit breaker status and graph topology
        </p>

        {/* Circuit breaker cards */}
        <div className="mb-8">
          <h2 className="text-lg font-medium mb-3 flex items-center gap-2">
            <Zap size={18} />
            Circuit Breakers
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {agents.map(agent => {
              const circuit = circuits[agent.agent_id]
              return (
                <Card key={agent.agent_id}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">{agent.agent_id}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {circuit?.circuit ? (
                      <div className="space-y-2">
                        <div className={`inline-flex rounded-md border px-2.5 py-0.5 text-xs font-medium ${stateColor(circuit.circuit.enabled)}`}>
                          {circuit.circuit.enabled ? 'Active' : 'Disabled'}
                        </div>
                        <div className="text-xs text-muted-foreground space-y-0.5">
                          <p>Failure threshold: {circuit.circuit.failure_threshold}</p>
                          <p>Recovery timeout: {circuit.circuit.recovery_timeout}s</p>
                        </div>
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground">No circuit breaker</span>
                    )}
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </div>

        {/* Graph visualization */}
        <div>
          <h2 className="text-lg font-medium mb-3 flex items-center gap-2">
            <Activity size={18} />
            Graph Topology
          </h2>
          <div className="mb-3">
            <Select value={selectedAgent} onValueChange={setSelectedAgent}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="Select agent" />
              </SelectTrigger>
              <SelectContent>
                {agents.map(a => (
                  <SelectItem key={a.agent_id} value={a.agent_id}>
                    {a.agent_id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="rounded-lg border border-border bg-muted/30 p-4">
            {mermaidCode ? (
              <div ref={mermaidRef} className="flex justify-center overflow-auto" />
            ) : (
              <p className="text-center text-sm text-muted-foreground py-8">
                {selectedAgent ? 'No graph data available' : 'Select an agent'}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
