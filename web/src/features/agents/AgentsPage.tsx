import { useState, useEffect } from 'react'
import { api, type AgentInfo, type CircuitStatus, type MemoryConfig } from '@/lib/api'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Card } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { Bot, Plus, ChevronDown, ChevronRight, Settings, Zap, GitBranch, FileText, Pencil, Trash2, Wrench, Brain } from 'lucide-react'

const DEFAULT_CLASSIFY_PROMPT = `\
You are an intent classifier. Your ONLY job is to read the user message and \
classify it into exactly one of the allowed intents listed below.

## Allowed intents
{intents}

## Scoring criteria
仅评估用户意图是否清晰指向某个 allowed intent，不评估意图要执行的具体内容。
- 0.8–1.0：用户意图明确，与某个 allowed intent 高度匹配
- 0.5–0.8：用户意图可推断，但表述模糊或存在歧义
- 0.0–0.5：无法判断用户意图，或消息内容完全无法与任何 intent 关联

## Rules
1. 先在 reasoning 中完成以下思考：
   - 提取：用户消息中表达意图的关键语义是什么？实际要处理的内容是什么？
   - 匹配：意图关键词指向哪个 intent？
   - 评分：仅按意图指向的清晰度评分，不考虑内容是否有意义。
2. Choose the single best-matching intent from the list above.
3. 按上述标准评估 confidence，严格打分，不要虚高。
4. Respond with ONLY a JSON object — no markdown, no explanation, no extra text.
5. JSON schema: {"reasoning": "<思考过程>", "intent": "<one of the allowed intents>", "confidence": <0.0-1.0>}

Now classify the user message. Return ONLY the JSON object.`

export function AgentsPage() {
  const { t } = useTranslation()
  const MODEL_FIELDS = [
    { key: 'provider', label: t('agents.model.provider') },
    { key: 'name', label: t('agents.model.modelName') },
    { key: 'api_key', label: t('agents.model.apiKey'), sensitive: true },
    { key: 'base_url', label: t('agents.model.baseUrl') },
    { key: 'temperature', label: t('agents.model.temperature') },
    { key: 'timeout', label: t('agents.model.timeout') },
    { key: 'max_tokens', label: t('agents.model.maxTokens') },
  ]

  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null)
  const [circuitMap, setCircuitMap] = useState<Record<string, CircuitStatus>>({})
  const [loading, setLoading] = useState(true)

  // Unified dialog state (add + edit)
  const [dialogMode, setDialogMode] = useState<'add' | 'edit' | null>(null)
  const [dialogAgentId, setDialogAgentId] = useState('')
  const [editTab, setEditTab] = useState('model')
  const [editForm, setEditForm] = useState<Record<string, unknown>>({})
  const [saving, setSaving] = useState(false)

  const loadAgents = async () => {
    try {
      setLoading(true)
      const list = await api.listAgents()
      setAgents(list)

      const circuits: Record<string, CircuitStatus> = {}
      await Promise.all(
        list.map(async agent => {
          try {
            circuits[agent.agent_id] = await api.getCircuitStatus(agent.agent_id)
          } catch { /* no circuit */ }
        })
      )
      setCircuitMap(circuits)
    } catch (err) {
      console.error('Failed to load agents:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadAgents() }, [])

  const openAdd = () => {
    setDialogMode('add')
    setDialogAgentId('')
    setEditTab('model')
    setEditForm({
      agent_id: '',
      provider: '',
      name: '',
      api_key: '',
      base_url: '',
      temperature: '',
      timeout: '',
      max_tokens: '',
    })
  }

  const openEdit = (agent: AgentInfo, tab: string) => {
    setDialogMode('edit')
    setDialogAgentId(agent.agent_id)
    setEditTab(tab)
    if (tab === 'model') {
      setEditForm({ ...(typeof agent.model === 'object' ? agent.model as Record<string, unknown> : {}) })
    } else if (tab === 'routing') {
      const descs = { ...(agent.intent_descriptions ?? {}) }
      setEditForm({
        intent_map: { ...(agent.intent_map ?? {}) },
        intent_descriptions: descs,
        confidence_threshold: agent.confidence_threshold ?? 0.7,
      })
    } else if (tab === 'prompts') {
      setEditForm({ classify_prompt: agent.prompts?.classify || DEFAULT_CLASSIFY_PROMPT })
    } else if (tab === 'defaultResponses') {
      setEditForm({
        default_responses: {
          clarify: agent.default_responses?.clarify || '抱歉，我不太确定您的意思，请再描述一下您的需求？',
          fallback: agent.default_responses?.fallback || '抱歉，我暂时无法处理这个请求，请尝试换一种描述方式？',
        }
      })
    } else if (tab === 'circuit') {
      const c = circuitMap[agent.agent_id]?.circuit
      setEditForm({
        circuit: {
          enabled: c?.enabled ?? true,
          failure_threshold: c?.failure_threshold ?? 5,
          recovery_timeout: c?.recovery_timeout ?? 60,
        },
      })
    } else if (tab === 'sub-agents') {
      // Normalize: strings → {name, public: true}, dicts keep as-is
      const refs = (agent.sub_agent_refs ?? []).map((ref: unknown) => {
        if (typeof ref === 'string') return { name: ref, public: true }
        return { ...(ref as Record<string, unknown>) }
      })
      setEditForm({ sub_agent_refs: refs })
    } else if (tab === 'memory') {
      const m = agent.memory
      setEditForm({
        memory: {
          l2: m?.l2 ?? true,
          l3: m?.l3 ?? true,
          context_window: {
            enabled: m?.context_window?.enabled ?? false,
            strategy: m?.context_window?.strategy ?? 'none',
            trigger_tokens: m?.context_window?.trigger_tokens ?? 100000,
            keep_messages: m?.context_window?.keep_messages ?? 20,
          },
          extraction: {
            enabled: m?.extraction?.enabled ?? false,
            max_messages: m?.extraction?.max_messages ?? 10,
            write_on: m?.extraction?.write_on ?? 'every_request',
          },
          retention: {
            knowledge_ttl_days: m?.retention?.knowledge_ttl_days ?? null,
            max_items_per_namespace: m?.retention?.max_items_per_namespace ?? null,
          },
        },
      })
    }
  }

  const handleSave = async () => {
    if (!dialogMode) return
    setSaving(true)
    try {
      let payload: Record<string, unknown>
      if (editTab === 'routing') {
        const intentMap = editForm.intent_map as Record<string, string>
        const descs = editForm.intent_descriptions as Record<string, string> ?? {}
        const richIntents: Record<string, { target: string; description?: string }> = {}
        for (const [k, v] of Object.entries(intentMap)) {
          richIntents[k] = { target: v }
          if (descs[k]) richIntents[k].description = descs[k]
        }
        payload = {
          intent_map: richIntents as unknown as Record<string, string>,
          confidence_threshold: editForm.confidence_threshold as number ?? 0.7,
        }
      } else if (editTab === 'model') {
        payload = { model: editForm }
      } else if (editTab === 'prompts') {
        payload = { prompts: { classify: (editForm.classify_prompt as string) ?? '' } }
      } else if (editTab === 'sub-agents') {
        const refs = ((editForm.sub_agent_refs as unknown[]) ?? []).map((ref: unknown) => {
          const r = ref as Record<string, unknown>
          if (r.public) return r.name as string
          return { name: r.name, public: false, strategy: r.strategy || 'react', tools: r.tools || [], system_prompt: r.system_prompt || '', strategy_config: r.strategy_config || {} }
        })
        payload = { sub_agent_refs: refs }
      } else if (editTab === 'memory') {
        payload = { memory: editForm.memory }
      } else if (editTab === 'defaultResponses') {
        payload = { default_responses: editForm.default_responses }
      } else {
        payload = editForm
      }

      if (dialogMode === 'add') {
        const agentId = (editForm.agent_id as string) || dialogAgentId
        if (!agentId) return
        await api.registerAgentJson({ agent_id: agentId, ...payload })
      } else {
        await api.updateAgent(dialogAgentId, payload)
      }
      setDialogMode(null)
      loadAgents()
    } catch (err) {
      console.error('Failed to save:', err)
    } finally {
      setSaving(false)
    }
  }

  const agent = agents.find(a => a.agent_id === dialogAgentId)

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold">{t('agents.title')}</h1>
            <p className="text-sm text-muted-foreground mt-1">{t('agents.subtitle')}</p>
          </div>
          <Button onClick={openAdd}><Plus size={16} className="mr-1" /> {t('agents.register')}</Button>
        </div>

        {loading ? (
          <div className="text-center py-12 text-muted-foreground">{t('agents.loading')}</div>
        ) : (
          <div className="space-y-3">
            {agents.map(agent => {
              const circuit = circuitMap[agent.agent_id]
              const isExpanded = expandedAgent === agent.agent_id

              return (
                <Card key={agent.agent_id} className="overflow-hidden">
                  {/* Summary row */}
                  <button
                    className="w-full flex items-center gap-4 p-4 text-left hover:bg-accent/30 transition-colors"
                    onClick={() => setExpandedAgent(isExpanded ? null : agent.agent_id)}
                  >
                    {isExpanded ? <ChevronDown size={16} className="text-muted-foreground shrink-0" /> : <ChevronRight size={16} className="text-muted-foreground shrink-0" />}
                    <Bot size={16} className="text-primary shrink-0" />
                    <span className="font-semibold min-w-[140px]">{agent.agent_id}</span>
                    <Badge variant="outline" className="font-mono">
                      {typeof agent.model === 'object' && agent.model?.name ? String(agent.model.name) : t('agents.defaultModel')}
                    </Badge>
                    <div className="flex gap-1 flex-1">
                      {agent.sub_agent_refs?.map((ref: unknown, i: number) => (
                        <Badge key={i} variant="secondary" className="text-xs">{typeof ref === 'string' ? ref : (ref as Record<string,unknown>).name as string}</Badge>
                      ))}
                    </div>
                    {circuit?.circuit && (
                      <Badge variant={circuit.circuit.enabled ? 'default' : 'secondary'}>
                        <Zap size={12} className="mr-1" />
                        {circuit.circuit.enabled ? t('agents.circuitOn') : t('agents.circuitOff')}
                      </Badge>
                    )}
                    {agent.memory && (
                      <Badge variant="outline">
                        <Brain size={12} className="mr-1" />
                        L2{agent.memory.l2 ? '✓' : '✗'} L3{agent.memory.l3 ? '✓' : '✗'}
                      </Badge>
                    )}
                    <span
                      className="ml-auto shrink-0 p-1 rounded hover:bg-destructive/10 cursor-pointer"
                      onClick={e => {
                        e.stopPropagation()
                        if (window.confirm(t('agents.deleteConfirm', { id: agent.agent_id }))) {
                          api.deleteAgent(agent.agent_id).then(loadAgents).catch(console.error)
                        }
                      }}
                      role="button"
                      tabIndex={0}
                    >
                      <Trash2 size={14} className="text-destructive" />
                    </span>
                  </button>

                  {/* Expanded detail */}
                  {isExpanded && (
                    <>
                      <Separator />
                      <div className="p-4 space-y-4 bg-muted/20">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-muted-foreground">{t('agents.agentConfig')}</span>
                          <Button variant="outline" size="sm" onClick={() => openEdit(agent, 'model')}>
                            <Pencil size={12} className="mr-1" /> {t('agents.edit')}
                          </Button>
                        </div>
                        {/* Model config */}
                        <SectionHeader icon={<Settings size={14} />} title={t('agents.model.title')} />
                        {typeof agent.model === 'object' && agent.model ? (
                          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                            {MODEL_FIELDS.map(({ key, label, sensitive }) => {
                              const value = (agent.model as Record<string, unknown>)[key]
                              if (value == null || value === '') return null
                              return (
                                <div key={key} className="rounded-md border border-border bg-background px-3 py-2">
                                  <div className="text-xs text-muted-foreground">{label}</div>
                                  <div className="text-sm font-medium truncate">
                                    {sensitive ? '••••••••' : String(value)}
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        ) : (
                          <p className="text-sm text-muted-foreground">{t('agents.model.defaultConfig')}</p>
                        )}

                        {/* Sub-agents */}
                        {agent.sub_agent_refs && agent.sub_agent_refs.length > 0 && (
                          <div>
                            <h4 className="text-sm font-medium flex items-center gap-2 mb-2">
                              <Wrench size={14} /> {t('agents.subAgents.title')}
                            </h4>
                            <div className="flex gap-2 flex-wrap">
                              {agent.sub_agent_refs.map((ref: unknown, i: number) => (
                                <Badge key={i} variant="secondary">{typeof ref === 'string' ? ref : (ref as Record<string,unknown>).name as string}</Badge>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Routing */}
                        {(agent.intent_map && Object.keys(agent.intent_map).length > 0 || agent.confidence_threshold != null) && (
                          <div>
                            <SectionHeader icon={<GitBranch size={14} />} title={t('agents.routing.title')}
                              subtile={t('agents.routing.threshold', { value: agent.confidence_threshold ?? '-' })}
                              />
                            <div className="rounded-lg border border-border overflow-hidden">
                              <Table>
                                <TableHeader>
                                  <TableRow>
                                    <TableHead className="w-1/2">{t('agents.routing.intent')}</TableHead>
                                    <TableHead>{t('agents.routing.targetSubAgent')}</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {Object.entries(agent.intent_map ?? {}).map(([intent, target]) => (
                                    <TableRow key={intent}>
                                      <TableCell className="text-sm">{intent}</TableCell>
                                      <TableCell>
                                        <Badge variant="secondary">{String(target)}</Badge>
                                      </TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            </div>
                          </div>
                        )}

                        {/* Default responses */}
                        {agent.default_responses && Object.keys(agent.default_responses).length > 0 && (
                          <div>
                            <SectionHeader icon={<FileText size={14} />} title={t('agents.defaultResponses.title')} />
                            <div className="space-y-2">
                              {Object.entries(agent.default_responses).map(([key, value]) => (
                                <div key={key} className="rounded-md border border-border bg-background p-3">
                                  <div className="text-xs text-muted-foreground mb-1 font-medium capitalize">{key}</div>
                                  <div className="text-sm whitespace-pre-wrap">{value}</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Circuit Breaker */}
                        <div>
                          <SectionHeader icon={<Zap size={14} />} title={t('agents.circuit.title')}
                            />
                          {circuit?.circuit ? (
                            <div className="flex gap-3">
                              <InfoBlock label={t('agents.circuit.status')} value={circuit.circuit.enabled ? t('agents.circuit.enabled') : t('agents.circuit.disabled')}
                                accent={circuit.circuit.enabled} />
                              <InfoBlock label={t('agents.circuit.failureThreshold')} value={String(circuit.circuit.failure_threshold)} />
                              <InfoBlock label={t('agents.circuit.recoveryTimeout')} value={`${circuit.circuit.recovery_timeout}s`} />
                            </div>
                          ) : (
                            <p className="text-sm text-muted-foreground">{t('agents.circuit.defaultCircuit')}</p>
                          )}
                        </div>

                        {/* Prompts */}
                        {agent.prompts && Object.keys(agent.prompts).length > 0 && (
                          <div>
                            <SectionHeader icon={<FileText size={14} />} title={t('agents.prompts.title')}
                              />
                            <div className="space-y-2">
                              {Object.entries(agent.prompts).map(([key, value]) => (
                                <div key={key} className="rounded-md border border-border bg-background p-3">
                                  <div className="text-xs text-muted-foreground mb-1 font-medium capitalize">{key}</div>
                                  <div className="text-sm whitespace-pre-wrap">
                                    {value || <span className="text-muted-foreground italic">{t('agents.prompts.empty')}</span>}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </Card>
              )
            })}

            {agents.length === 0 && (
              <div className="text-center py-12 text-muted-foreground">{t('agents.noAgents')}</div>
            )}
          </div>
        )}

        {/* Edit Dialog */}
        <Dialog open={dialogMode != null} onOpenChange={(open) => { if (!open) setDialogMode(null) }}>
          <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>
                {dialogMode === 'add' ? t('agents.register') : t('agents.editTitle', { agent: dialogAgentId })}
              </DialogTitle>
            </DialogHeader>
            {dialogMode === 'add' && (
              <div className="mb-3">
                <label className="text-sm font-medium">Agent ID</label>
                <Input
                  value={editForm.agent_id as string ?? ''}
                  onChange={e => setEditForm(f => ({ ...f, agent_id: e.target.value }))}
                  className="mt-1 font-mono text-sm"
                  placeholder="my_agent"
                />
              </div>
            )}
            <Tabs value={editTab} onValueChange={tab => {
              if (dialogMode === 'edit' && agent) openEdit(agent, tab)
            }}>
              <TabsList>
                <TabsTrigger value="model">{t('agents.model.tab')}</TabsTrigger>
                <TabsTrigger value="routing">{t('agents.routing.tab')}</TabsTrigger>
                <TabsTrigger value="prompts">{t('agents.prompts.tab')}</TabsTrigger>
                <TabsTrigger value="circuit">{t('agents.circuit.tab')}</TabsTrigger>
                <TabsTrigger value="defaultResponses">{t('agents.defaultResponses.tab')}</TabsTrigger>
                <TabsTrigger value="sub-agents">{t('agents.subAgents.tab')}</TabsTrigger>
                <TabsTrigger value="memory">{t('agents.memory.tab')}</TabsTrigger>
              </TabsList>

              <TabsContent value="model" className="space-y-3 mt-3">
                {MODEL_FIELDS.map(({ key, label, sensitive }) => (
                  <div key={key}>
                    <label className="text-sm font-medium">{label}</label>
                    <Input
                      type={sensitive ? 'password' : 'text'}
                      value={(editForm[key] as string) ?? ''}
                      onChange={e => setEditForm(f => ({ ...f, [key]: e.target.value }))}
                      className="mt-1 font-mono text-sm"
                    />
                  </div>
                ))}
              </TabsContent>

              <TabsContent value="routing" className="space-y-3 mt-3">
                <div>
                  <label className="text-sm font-medium">{t('agents.routing.confidenceThreshold')}</label>
                  <Input
                    type="number"
                    step="0.1"
                    min="0"
                    max="1"
                    value={String(editForm.confidence_threshold ?? 0.7)}
                    onChange={e => setEditForm(f => ({ ...f, confidence_threshold: parseFloat(e.target.value) }))}
                    className="mt-1 font-mono text-sm w-32"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium mb-2 block">{t('agents.routing.intentMapping')}</label>
                  <div className="space-y-3">
                    {Object.entries((editForm.intent_map as Record<string, string>) ?? {}).map(([intent, target]) => {
                      const descs = (editForm.intent_descriptions as Record<string, string>) ?? {}
                      return (
                      <div key={intent} className="rounded border border-border p-2 space-y-1.5">
                        <div className="flex gap-2 items-center">
                          <Input
                            value={intent}
                            onChange={e => {
                              const newMap = { ...(editForm.intent_map as Record<string, string>) }
                              const newDescs = { ...descs }
                              delete newMap[intent]
                              newMap[e.target.value] = target
                              newDescs[e.target.value] = newDescs[intent] || ''
                              delete newDescs[intent]
                              setEditForm(f => ({ ...f, intent_map: newMap, intent_descriptions: newDescs }))
                            }}
                            className="font-mono text-sm flex-1"
                            placeholder={t('agents.routing.intentNamePlaceholder')}
                          />
                          <span className="text-muted-foreground">→</span>
                          <Input
                            value={target}
                            onChange={e => {
                              const newMap = { ...(editForm.intent_map as Record<string, string>) }
                              newMap[intent] = e.target.value
                              setEditForm(f => ({ ...f, intent_map: newMap }))
                            }}
                            className="font-mono text-sm flex-1"
                            placeholder={t('agents.routing.subAgentPlaceholder')}
                          />
                          <Button variant="ghost" size="sm" onClick={() => {
                            const newMap = { ...(editForm.intent_map as Record<string, string>) }
                            const newDescs = { ...descs }
                            delete newMap[intent]
                            delete newDescs[intent]
                            setEditForm(f => ({ ...f, intent_map: newMap, intent_descriptions: newDescs }))
                          }}>
                            <Trash2 size={14} className="text-destructive" />
                          </Button>
                        </div>
                        <Input
                          value={descs[intent] || ''}
                          onChange={e => {
                            const newDescs = { ...descs }
                            newDescs[intent] = e.target.value
                            setEditForm(f => ({ ...f, intent_descriptions: newDescs }))
                          }}
                          className="text-xs w-full"
                          placeholder={t('agents.routing.descriptionPlaceholder')}
                        />
                      </div>
                    )})}
                    <Button variant="outline" size="sm" onClick={() => {
                      const newMap = { ...(editForm.intent_map as Record<string, string>), '': '' }
                      setEditForm(f => ({ ...f, intent_map: newMap }))
                    }}>
                      <Plus size={14} className="mr-1" /> {t('agents.routing.addIntent')}
                    </Button>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="prompts" className="space-y-3 mt-3">
                <p className="text-sm text-muted-foreground">{t('agents.prompts.description')}</p>
                <div>
                  <label className="text-sm font-medium">{t('agents.prompts.classifyLabel')}</label>
                  <textarea
                    value={(editForm.classify_prompt as string) ?? ''}
                    onChange={e => setEditForm(f => ({ ...f, classify_prompt: e.target.value }))}
                    className="w-full h-48 mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm font-mono resize-none"
                    placeholder={t('agents.prompts.classifyHint')}
                  />
                </div>
                <details className="rounded-md border border-border bg-muted/30 p-3">
                  <summary className="text-sm font-medium cursor-pointer">{t('agents.prompts.tipsTitle')}</summary>
                  <ul className="mt-2 space-y-1.5 list-disc list-inside text-xs text-muted-foreground">
                    <li>{t('agents.prompts.tip1')}</li>
                    <li>{t('agents.prompts.tip2')}</li>
                    <li>{t('agents.prompts.tip3')}</li>
                    <li>{t('agents.prompts.tip4')}</li>
                  </ul>
                </details>
              </TabsContent>

              <TabsContent value="defaultResponses" className="space-y-3 mt-3">
                <p className="text-sm text-muted-foreground">{t('agents.defaultResponses.description')}</p>
                <div>
                  <label className="text-sm font-medium">{t('agents.defaultResponses.clarify')}</label>
                  <textarea
                    value={(editForm.default_responses as Record<string, string>)?.clarify ?? ''}
                    onChange={e => setEditForm(f => ({
                      ...f,
                      default_responses: { ...(f.default_responses as Record<string, string>), clarify: e.target.value }
                    }))}
                    className="w-full h-24 mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
                    placeholder={t('agents.defaultResponses.clarifyPlaceholder')}
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">{t('agents.defaultResponses.fallback')}</label>
                  <textarea
                    value={(editForm.default_responses as Record<string, string>)?.fallback ?? ''}
                    onChange={e => setEditForm(f => ({
                      ...f,
                      default_responses: { ...(f.default_responses as Record<string, string>), fallback: e.target.value }
                    }))}
                    className="w-full h-24 mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
                    placeholder={t('agents.defaultResponses.fallbackPlaceholder')}
                  />
                </div>
              </TabsContent>

              <TabsContent value="circuit" className="space-y-3 mt-3">
                <div className="flex items-center gap-3">
                  <label className="text-sm font-medium">{t('agents.circuit.enabled')}</label>
                  <input
                    type="checkbox"
                    checked={(editForm.circuit as Record<string, unknown>)?.enabled as boolean ?? true}
                    onChange={e => setEditForm(f => ({
                      ...f,
                      circuit: { ...(f.circuit as Record<string, unknown>), enabled: e.target.checked }
                    }))}
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">{t('agents.circuit.failureThreshold')}</label>
                  <Input
                    type="number"
                    value={String((editForm.circuit as Record<string, unknown>)?.failure_threshold ?? 5)}
                    onChange={e => setEditForm(f => ({
                      ...f,
                      circuit: { ...(f.circuit as Record<string, unknown>), failure_threshold: parseInt(e.target.value) }
                    }))}
                    className="mt-1 font-mono text-sm w-32"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">{t('agents.circuit.recoveryTimeoutSec')}</label>
                  <Input
                    type="number"
                    value={String((editForm.circuit as Record<string, unknown>)?.recovery_timeout ?? 60)}
                    onChange={e => setEditForm(f => ({
                      ...f,
                      circuit: { ...(f.circuit as Record<string, unknown>), recovery_timeout: parseInt(e.target.value) }
                    }))}
                    className="mt-1 font-mono text-sm w-32"
                  />
                </div>
              </TabsContent>

              <TabsContent value="sub-agents" className="space-y-3 mt-3">
                {((editForm.sub_agent_refs as Record<string, unknown>[]) ?? []).map((ref, i) => {
                  const isPublic = ref.public as boolean ?? true
                  const update = (patch: Record<string, unknown>) => {
                    const newRefs = [...((editForm.sub_agent_refs as Record<string, unknown>[]) ?? [])]
                    newRefs[i] = { ...newRefs[i], ...patch }
                    setEditForm(f => ({ ...f, sub_agent_refs: newRefs }))
                  }
                  const remove = () => {
                    const newRefs = ((editForm.sub_agent_refs as Record<string, unknown>[]) ?? []).filter((_, j) => j !== i)
                    setEditForm(f => ({ ...f, sub_agent_refs: newRefs }))
                  }
                  return (
                    <div key={i} className="rounded-md border border-border p-3 space-y-2">
                      <div className="flex items-center gap-2">
                        <Input
                          value={(ref.name as string) ?? ''}
                          onChange={e => update({ name: e.target.value })}
                          className="font-mono text-sm flex-1"
                          placeholder={t('agents.subAgents.namePlaceholder')}
                        />
                        <select
                          value={isPublic ? 'public' : 'inline'}
                          onChange={e => update({ public: e.target.value === 'public' })}
                          className="text-xs rounded-md border border-input bg-background px-2 py-1"
                        >
                          <option value="public">{t('agents.subAgents.public')}</option>
                          <option value="inline">{t('agents.subAgents.inline')}</option>
                        </select>
                        <Button variant="ghost" size="sm" onClick={remove}>
                          <Trash2 size={14} className="text-destructive" />
                        </Button>
                      </div>
                      {!isPublic && (ref.strategy as string) !== 'dsl' && (
                        <div className="space-y-2 pl-2 border-l-2 border-primary/30">
                          <div>
                            <label className="text-xs text-muted-foreground">{t('agents.subAgents.strategy')}</label>
                            <select
                              value={(ref.strategy as string) ?? 'react'}
                              onChange={e => update({ strategy: e.target.value })}
                              className="w-full mt-0.5 text-sm rounded-md border border-input bg-background px-2 py-1 font-mono"
                            >
                              <option value="react">react</option>
                              <option value="function_calling">function_calling</option>
                              <option value="dsl">dsl</option>
                            </select>
                          </div>
                          <div>
                            <label className="text-xs text-muted-foreground">{t('agents.subAgents.toolsLabel')}</label>
                            <Input
                              value={((ref.tools as string[]) ?? []).join(', ')}
                              onChange={e => update({ tools: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                              className="mt-0.5 font-mono text-sm"
                              placeholder={t('agents.subAgents.toolsPlaceholder')}
                            />
                          </div>
                          <div>
                            <label className="text-xs text-muted-foreground">{t('agents.subAgents.systemPrompt')}</label>
                            <textarea
                              value={(ref.system_prompt as string) ?? ''}
                              onChange={e => update({ system_prompt: e.target.value })}
                              className="w-full h-24 mt-0.5 rounded-md border border-input bg-background px-2 py-1 text-xs font-mono resize-none"
                              placeholder={t('agents.subAgents.systemPromptPlaceholder')}
                            />
                          </div>
                        </div>
                      )}
                      {!isPublic && (ref.strategy as string) === 'dsl' && (
                        <div className="space-y-2 pl-2 border-l-2 border-primary/30">
                          <div>
                            <label className="text-xs text-muted-foreground">{t('agents.subAgents.strategy')}</label>
                            <select
                              value="dsl"
                              onChange={e => update({ strategy: e.target.value })}
                              className="w-full mt-0.5 text-sm rounded-md border border-input bg-background px-2 py-1 font-mono"
                            >
                              <option value="react">react</option>
                              <option value="function_calling">function_calling</option>
                              <option value="dsl">dsl</option>
                            </select>
                          </div>
                          <GraphEditor
                            graph={(ref.graph as Record<string, unknown>) ?? { nodes: {}, edges: [] }}
                            onChange={(g) => update({ graph: g, tools: [], system_prompt: '' })}
                          />
                        </div>
                      )}
                    </div>
                  )
                })}
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => {
                    const newRefs = [...((editForm.sub_agent_refs as unknown[]) ?? []), { name: '', public: true }]
                    setEditForm(f => ({ ...f, sub_agent_refs: newRefs }))
                  }}>
                    <Plus size={14} className="mr-1" /> {t('agents.subAgents.addPublic')}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => {
                    const newRefs = [...((editForm.sub_agent_refs as unknown[]) ?? []), { name: '', public: false, strategy: 'react', tools: [], system_prompt: '' }]
                    setEditForm(f => ({ ...f, sub_agent_refs: newRefs }))
                  }}>
                    <Plus size={14} className="mr-1" /> {t('agents.subAgents.addInline')}
                  </Button>
                </div>
              </TabsContent>

              <TabsContent value="memory" className="space-y-4 mt-3">
                {(() => {
                  const m = (editForm.memory ?? {}) as MemoryConfig
                  const updateMemory = (patch: Partial<MemoryConfig>) =>
                    setEditForm(f => ({ ...f, memory: { ...(f.memory as MemoryConfig), ...patch } }))
                  const cw = m.context_window ?? {}
                  const updateCW = (patch: Record<string, unknown>) =>
                    setEditForm(f => ({ ...f, memory: { ...(f.memory as MemoryConfig), context_window: { ...(f.memory as MemoryConfig).context_window, ...patch } } }))
                  const ext = m.extraction ?? {}
                  const updateExt = (patch: Record<string, unknown>) =>
                    setEditForm(f => ({ ...f, memory: { ...(f.memory as MemoryConfig), extraction: { ...(f.memory as MemoryConfig).extraction, ...patch } } }))
                  const ret = m.retention ?? {}
                  const updateRet = (patch: Record<string, unknown>) =>
                    setEditForm(f => ({ ...f, memory: { ...(f.memory as MemoryConfig), retention: { ...(f.memory as MemoryConfig).retention, ...patch } } }))

                  return (
                    <>
                      {/* ── L2 Session Memory ── */}
                      <div className="rounded-md border-2 border-blue-500/30 bg-blue-500/5 p-3 space-y-2">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="inline-flex items-center justify-center rounded bg-blue-500 text-white text-xs font-bold px-1.5 py-0.5">L2</span>
                          <span className="text-sm font-semibold">{t('agents.memory.l2Title')}</span>
                          <span className="text-xs text-muted-foreground">{t('agents.memory.l2Subtitle')}</span>
                        </div>
                        <p className="text-xs text-muted-foreground pl-1">{t('agents.memory.l2Desc')}</p>
                        <div className="flex items-center gap-3">
                          <input type="checkbox" checked={m.l2 ?? true} onChange={e => updateMemory({ l2: e.target.checked })} />
                          <label className="text-sm">{t('agents.memory.l2Enable')}</label>
                        </div>
                      </div>

                      {/* ── L3 Long-term Memory ── */}
                      <div className="rounded-md border-2 border-purple-500/30 bg-purple-500/5 p-3 space-y-3">
                        <div className="flex items-center gap-2">
                          <span className="inline-flex items-center justify-center rounded bg-purple-500 text-white text-xs font-bold px-1.5 py-0.5">L3</span>
                          <span className="text-sm font-semibold">{t('agents.memory.l3Title')}</span>
                          <span className="text-xs text-muted-foreground">{t('agents.memory.l3Subtitle')}</span>
                        </div>
                        <p className="text-xs text-muted-foreground pl-1">{t('agents.memory.l3Desc')}</p>
                        <div className="flex items-center gap-3">
                          <input type="checkbox" checked={m.l3 ?? true} onChange={e => updateMemory({ l3: e.target.checked })} />
                          <label className="text-sm">{t('agents.memory.l3Enable')}</label>
                        </div>

                        {/* Context Window — L3 */}
                        <div className="rounded-md border border-border bg-background p-3 space-y-2">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] text-muted-foreground border rounded px-1 py-0.5">L3</span>
                            <div className="flex items-center gap-3">
                              <input type="checkbox" checked={cw.enabled ?? false} onChange={e => updateCW({ enabled: e.target.checked })} />
                              <label className="text-sm font-medium">{t('agents.memory.cwTitle')}</label>
                            </div>
                          </div>
                          <div className="grid grid-cols-2 gap-3 pl-6">
                            <div>
                              <label className="text-xs text-muted-foreground">{t('agents.memory.strategy')}</label>
                              <select
                                value={cw.strategy ?? 'none'}
                                onChange={e => updateCW({ strategy: e.target.value })}
                                className="w-full mt-0.5 text-sm rounded-md border border-input bg-background px-2 py-1 font-mono"
                              >
                                <option value="none">none</option>
                                <option value="summarize">summarize</option>
                                <option value="trim">trim</option>
                              </select>
                            </div>
                            <div>
                              <label className="text-xs text-muted-foreground">{t('agents.memory.triggerTokens')}</label>
                              <Input
                                type="number"
                                value={String(cw.trigger_tokens ?? 100000)}
                                onChange={e => updateCW({ trigger_tokens: parseInt(e.target.value) || 100000 })}
                                className="mt-0.5 font-mono text-sm"
                              />
                            </div>
                            <div>
                              <label className="text-xs text-muted-foreground">{t('agents.memory.keepMessages')}</label>
                              <Input
                                type="number"
                                value={String(cw.keep_messages ?? 20)}
                                onChange={e => updateCW({ keep_messages: parseInt(e.target.value) || 20 })}
                                className="mt-0.5 font-mono text-sm"
                              />
                            </div>
                          </div>
                        </div>

                        {/* Extraction — L3 */}
                        <div className="rounded-md border border-border bg-background p-3 space-y-2">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] text-muted-foreground border rounded px-1 py-0.5">L3</span>
                            <div className="flex items-center gap-3">
                              <input type="checkbox" checked={ext.enabled ?? false} onChange={e => updateExt({ enabled: e.target.checked })} />
                              <label className="text-sm font-medium">{t('agents.memory.extractionTitle')}</label>
                            </div>
                          </div>
                          <div className="grid grid-cols-2 gap-3 pl-6">
                            <div>
                              <label className="text-xs text-muted-foreground">{t('agents.memory.maxMessages')}</label>
                              <Input
                                type="number"
                                value={String(ext.max_messages ?? 10)}
                                onChange={e => updateExt({ max_messages: parseInt(e.target.value) || 10 })}
                                className="mt-0.5 font-mono text-sm"
                              />
                            </div>
                            <div>
                              <label className="text-xs text-muted-foreground">{t('agents.memory.writeOn')}</label>
                              <select
                                value={ext.write_on ?? 'every_request'}
                                onChange={e => updateExt({ write_on: e.target.value })}
                                className="w-full mt-0.5 text-sm rounded-md border border-input bg-background px-2 py-1 font-mono"
                              >
                                <option value="every_request">every_request</option>
                                <option value="every_n_messages">every_n_messages</option>
                                <option value="end_of_session">end_of_session</option>
                                <option value="disabled">disabled</option>
                              </select>
                            </div>
                          </div>
                        </div>

                        {/* Retention — L3 */}
                        <div className="rounded-md border border-border bg-background p-3 space-y-2">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] text-muted-foreground border rounded px-1 py-0.5">L3</span>
                            <label className="text-sm font-medium">{t('agents.memory.retentionTitle')}</label>
                          </div>
                          <div className="grid grid-cols-2 gap-3 pl-6">
                            <div>
                              <label className="text-xs text-muted-foreground">{t('agents.memory.knowledgeTtl')}</label>
                              <Input
                                type="number"
                                value={ret.knowledge_ttl_days != null ? String(ret.knowledge_ttl_days) : ''}
                                onChange={e => updateRet({ knowledge_ttl_days: e.target.value ? parseInt(e.target.value) : null })}
                                placeholder={t('agents.memory.knowledgeTtlPlaceholder')}
                                className="mt-0.5 font-mono text-sm"
                              />
                            </div>
                            <div>
                              <label className="text-xs text-muted-foreground">{t('agents.memory.maxItems')}</label>
                              <Input
                                type="number"
                                value={ret.max_items_per_namespace != null ? String(ret.max_items_per_namespace) : ''}
                                onChange={e => updateRet({ max_items_per_namespace: e.target.value ? parseInt(e.target.value) : null })}
                                placeholder={t('agents.memory.maxItemsPlaceholder')}
                                className="mt-0.5 font-mono text-sm"
                              />
                            </div>
                          </div>
                        </div>
                      </div>
                    </>
                  )
                })()}
              </TabsContent>
            </Tabs>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="outline" onClick={() => setDialogMode(null)}>{t('agents.cancel')}</Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? t('agents.saving') : dialogMode === 'add' ? t('agents.registerAction') : t('agents.saveChanges')}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}

function SectionHeader({ icon, title, subtile }: {
  icon: React.ReactNode; title: string; subtile?: string
}) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <h4 className="text-sm font-medium flex items-center gap-2">
        {icon} {title}
      </h4>
      {subtile && (
        <Badge variant="outline" className="text-xs font-normal">{subtile}</Badge>
      )}
    </div>
  )
}

function InfoBlock({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-md border border-border bg-background px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-sm font-medium ${accent ? 'text-green-600' : ''}`}>{value}</div>
    </div>
  )
}

const NODE_TYPES = ['llm', 'tool', 'tools', 'sub_agent']

function GraphEditor({ graph, onChange }: { graph: Record<string, unknown>; onChange: (g: Record<string, unknown>) => void }) {
  const { t } = useTranslation()
  const nodes = (graph.nodes as Record<string, Record<string, unknown>>) ?? {}
  const edges = (graph.edges as Array<{ from: string; to: string }>) ?? []

  const updateNode = (name: string, patch: Record<string, unknown>) => {
    const newNodes = { ...nodes }
    newNodes[name] = { ...(newNodes[name] ?? {}), ...patch }
    onChange({ ...graph, nodes: newNodes })
  }
  const removeNode = (name: string) => {
    const newNodes = { ...nodes }
    delete newNodes[name]
    onChange({ ...graph, nodes: newNodes })
  }
  const addNode = () => {
    const newNodes = { ...nodes, '': { type: 'llm' } }
    onChange({ ...graph, nodes: newNodes })
  }
  const renameNode = (oldName: string, newName: string) => {
    const newNodes: Record<string, Record<string, unknown>> = {}
    for (const [k, v] of Object.entries(nodes)) {
      newNodes[k === oldName ? newName : k] = v
    }
    // Update edges referencing old name
    const newEdges = edges.map(e => ({
      ...e,
      from: e.from === oldName ? newName : e.from,
      to: e.to === oldName ? newName : e.to,
    }))
    onChange({ ...graph, nodes: newNodes, edges: newEdges })
  }

  const addEdge = () => onChange({ ...graph, edges: [...edges, { from: 'START', to: '' }] })
  const removeEdge = (i: number) => onChange({ ...graph, edges: edges.filter((_, j) => j !== i) })
  const updateEdge = (i: number, patch: Partial<{ from: string; to: string }>) => {
    const newEdges = [...edges]
    newEdges[i] = { ...newEdges[i], ...patch }
    onChange({ ...graph, edges: newEdges })
  }

  const nodeNames = ['START', 'END', ...Object.keys(nodes)]

  return (
    <div className="space-y-3">
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-xs text-muted-foreground">{t('agents.graphEditor.nodes', { count: Object.keys(nodes).length })}</label>
          <Button variant="ghost" size="sm" onClick={addNode}>
            <Plus size={12} className="mr-0.5" /> {t('agents.graphEditor.node')}
          </Button>
        </div>
        <div className="space-y-1.5">
          {Object.entries(nodes).map(([name, node], idx) => (
            <div key={idx} className="flex gap-1 items-start text-xs">
              <Input
                defaultValue={name}
                onBlur={e => { const v = e.target.value.trim(); if (v && v !== name) renameNode(name, v) }}
                className="font-mono text-xs h-7 w-24"
                placeholder={t('agents.graphEditor.namePlaceholder')}
              />
              <select
                value={(node.type as string) ?? 'llm'}
                onChange={e => updateNode(name, { type: e.target.value })}
                className="rounded border border-input bg-background px-1 py-0.5 text-xs font-mono h-7 w-18"
              >
                {NODE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
              {(node.type === 'llm' || node.type === 'tools') && (
                <Input
                  value={((node.tools as string[]) ?? []).join(',')}
                  onChange={e => updateNode(name, { tools: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                  className="font-mono text-xs h-7 flex-1"
                  placeholder={t('agents.graphEditor.toolsPlaceholder')}
                />
              )}
              {node.type === 'llm' && (
                <Input
                  value={(node.system_prompt as string) ?? ''}
                  onChange={e => updateNode(name, { system_prompt: e.target.value })}
                  className="font-mono text-xs h-7 flex-1"
                  placeholder={t('agents.graphEditor.promptPlaceholder')}
                />
              )}
              <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => removeNode(name)}>
                <Trash2 size={12} className="text-destructive" />
              </Button>
            </div>
          ))}
        </div>
      </div>
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-xs text-muted-foreground">{t('agents.graphEditor.edges', { count: edges.length })}</label>
          <Button variant="ghost" size="sm" onClick={addEdge}>
            <Plus size={12} className="mr-0.5" /> {t('agents.graphEditor.edge')}
          </Button>
        </div>
        <div className="space-y-1">
          {edges.map((e, i) => (
            <div key={i} className="flex gap-1 items-center text-xs">
              <select
                value={e.from}
                onChange={ev => updateEdge(i, { from: ev.target.value })}
                className="rounded border border-input bg-background px-1 py-0.5 text-xs font-mono h-7"
              >
                {nodeNames.map(n => <option key={n} value={n}>{n}</option>)}
              </select>
              <span className="text-muted-foreground">→</span>
              <select
                value={e.to}
                onChange={ev => updateEdge(i, { to: ev.target.value })}
                className="rounded border border-input bg-background px-1 py-0.5 text-xs font-mono h-7"
              >
                {nodeNames.map(n => <option key={n} value={n}>{n}</option>)}
              </select>
              <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => removeEdge(i)}>
                <Trash2 size={12} className="text-destructive" />
              </Button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
