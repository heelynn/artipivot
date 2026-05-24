import { useState, useEffect, useRef } from 'react'
import { api, type CircuitStatus } from '@/lib/api'
import type { AgentInfo } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useTranslation } from 'react-i18next'
import { Activity, Zap } from 'lucide-react'

export function ObservePage() {
  const { t } = useTranslation()
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
        <h1 className="text-2xl font-semibold mb-1">{t('observe.title')}</h1>
        <p className="text-sm text-muted-foreground mb-6">
          {t('observe.subtitle')}
        </p>

        {/* Circuit breaker cards */}
        <div className="mb-8">
          <h2 className="text-lg font-medium mb-3 flex items-center gap-2">
            <Zap size={18} />
            {t('observe.circuitBreakers')}
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
                          {circuit.circuit.enabled ? t('observe.active') : t('observe.disabled')}
                        </div>
                        <div className="text-xs text-muted-foreground space-y-0.5">
                          <p>{t('observe.failureThreshold', { value: circuit.circuit.failure_threshold })}</p>
                          <p>{t('observe.recoveryTimeout', { value: circuit.circuit.recovery_timeout })}</p>
                        </div>
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground">{t('observe.noCircuit')}</span>
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
            {t('observe.graphTopology')}
          </h2>
          <div className="mb-3">
            <Select value={selectedAgent} onValueChange={setSelectedAgent}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder={t('observe.selectAgent')} />
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
                {selectedAgent ? t('observe.noGraph') : t('observe.selectAgentPrompt')}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
