import { useState, useEffect } from 'react'
import { api, type ToolInfo, type SubAgentInfo, type RateLimitConfig } from '@/lib/api'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Card } from '@/components/ui/card'
import { Plus, Trash2, Pencil, ChevronDown, ChevronRight, Save, X } from 'lucide-react'

export function ConfigPage() {
  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl">
        <h1 className="text-2xl font-semibold mb-1">Configuration</h1>
        <p className="text-sm text-muted-foreground mb-6">
          Manage models, routing, rate limits, tools, and sub-agents
        </p>

        <Tabs defaultValue="tools">
          <TabsList className="mb-4">
            <TabsTrigger value="tools">Tools</TabsTrigger>
            <TabsTrigger value="sub-agents">Sub-Agents</TabsTrigger>
            <TabsTrigger value="ratelimits">Rate Limits</TabsTrigger>
          </TabsList>

          <TabsContent value="tools">
            <ToolsTab />
          </TabsContent>
          <TabsContent value="sub-agents">
            <SubAgentsTab />
          </TabsContent>
          <TabsContent value="ratelimits">
            <RateLimitsTab />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

// ── Tools tab ──

function ToolsTab() {
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [yamlInput, setYamlInput] = useState('')
  const [expandedTool, setExpandedTool] = useState<string | null>(null)
  const [editingTool, setEditingTool] = useState<ToolInfo | null>(null)
  const [editForm, setEditForm] = useState<Record<string, string>>({})

  const load = async () => {
    try {
      setTools(await api.listTools())
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    if (!yamlInput.trim()) return
    try {
      await api.createTool(yamlInput)
      setCreateOpen(false)
      setYamlInput('')
      load()
    } catch (err) {
      console.error(err)
    }
  }

  const handleDelete = async (name: string) => {
    try {
      await api.deleteTool(name)
      load()
    } catch (err) {
      console.error(err)
    }
  }

  const startEdit = (tool: ToolInfo) => {
    setEditingTool(tool)
    setEditForm({
      type: tool.type || 'builtin',
      module: tool.module || '',
      function: tool.function || '',
      config: tool.config ? JSON.stringify(tool.config, null, 2) : '{}',
    })
  }

  const handleSave = async () => {
    if (!editingTool) return
    try {
      let config = {}
      try { config = JSON.parse(editForm.config || '{}') } catch { /* keep as string */ }
      await api.updateTool(editingTool.name, {
        type: editForm.type,
        module: editForm.module,
        function: editForm.function,
        config,
        status: editingTool.status || 'active',
      })
      setEditingTool(null)
      load()
    } catch (err) {
      console.error(err)
    }
  }

  return (
    <>
      <div className="flex justify-end mb-3">
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button size="sm"><Plus size={14} className="mr-1" /> Add Tool</Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader><DialogTitle>Add Tool</DialogTitle></DialogHeader>
            <textarea
              value={yamlInput}
              onChange={e => setYamlInput(e.target.value)}
              placeholder="Paste tool YAML configuration..."
              className="w-full h-64 rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
              <Button onClick={handleCreate}>Create</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <p className="text-muted-foreground text-sm">Loading...</p>
      ) : (
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Module</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {tools.map(tool => {
                const isExpanded = expandedTool === tool.name
                return (
                  <>
                    <TableRow key={tool.name} className="cursor-pointer hover:bg-muted/30"
                      onClick={() => setExpandedTool(isExpanded ? null : tool.name)}>
                      <TableCell>
                        {isExpanded ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
                      </TableCell>
                      <TableCell className="font-medium font-mono text-sm">{tool.name}</TableCell>
                      <TableCell className="text-muted-foreground">{tool.type || '-'}</TableCell>
                      <TableCell className="text-muted-foreground text-xs font-mono">{tool.module || '-'}</TableCell>
                      <TableCell>
                        <Badge variant={tool.status === 'active' ? 'default' : 'secondary'}>
                          {tool.status || 'unknown'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="sm" onClick={e => { e.stopPropagation(); startEdit(tool) }}>
                            <Pencil size={14} />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={e => { e.stopPropagation(); handleDelete(tool.name) }}>
                            <Trash2 size={14} className="text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                    {isExpanded && (
                      <TableRow>
                        <TableCell colSpan={6} className="bg-muted/20 p-4">
                          <div className="grid grid-cols-2 gap-3">
                            {tool.function && <InfoField label="Function" value={tool.function} />}
                            {tool.config && Object.keys(tool.config).length > 0 && (
                              <InfoField label="Config" value={JSON.stringify(tool.config, null, 2)} mono />
                            )}
                            {!tool.function && (!tool.config || Object.keys(tool.config).length === 0) && (
                              <p className="text-sm text-muted-foreground col-span-2">No additional details</p>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                )
              })}
              {tools.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                    No tools registered
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Edit Tool Dialog */}
      <Dialog open={editingTool != null} onOpenChange={(open) => { if (!open) setEditingTool(null) }}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Edit {editingTool?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium">Type</label>
              <Input value={editForm.type || ''} onChange={e => setEditForm(f => ({ ...f, type: e.target.value }))}
                className="mt-1 font-mono text-sm" />
            </div>
            <div>
              <label className="text-sm font-medium">Module</label>
              <Input value={editForm.module || ''} onChange={e => setEditForm(f => ({ ...f, module: e.target.value }))}
                className="mt-1 font-mono text-sm" placeholder="my_pkg.tools.search" />
            </div>
            <div>
              <label className="text-sm font-medium">Function</label>
              <Input value={editForm.function || ''} onChange={e => setEditForm(f => ({ ...f, function: e.target.value }))}
                className="mt-1 font-mono text-sm" placeholder="my_function" />
            </div>
            <div>
              <label className="text-sm font-medium">Config (JSON)</label>
              <textarea value={editForm.config || '{}'}
                onChange={e => setEditForm(f => ({ ...f, config: e.target.value }))}
                className="w-full h-32 rounded-md border border-input bg-background px-3 py-2 text-xs font-mono resize-none mt-1" />
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="outline" onClick={() => setEditingTool(null)}>
              <X size={14} className="mr-1" /> Cancel
            </Button>
            <Button onClick={handleSave}>
              <Save size={14} className="mr-1" /> Save Changes
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

// ── Sub-Agents tab ──

function SubAgentsTab() {
  const [subAgents, setSubAgents] = useState<SubAgentInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [yamlInput, setYamlInput] = useState('')
  const [expandedSA, setExpandedSA] = useState<string | null>(null)
  const [editingSA, setEditingSA] = useState<SubAgentInfo | null>(null)
  const [editForm, setEditForm] = useState<Record<string, string>>({})

  const load = async () => {
    try {
      setSubAgents(await api.listSubAgents())
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    if (!yamlInput.trim()) return
    try {
      await api.createSubAgent(yamlInput)
      setCreateOpen(false)
      setYamlInput('')
      load()
    } catch (err) {
      console.error(err)
    }
  }

  const handleDelete = async (name: string) => {
    try {
      await api.deleteSubAgent(name)
      load()
    } catch (err) {
      console.error(err)
    }
  }

  const startEdit = (sa: SubAgentInfo) => {
    setEditingSA(sa)
    setEditForm({
      strategy: sa.strategy || 'react',
      system_prompt: sa.system_prompt || '',
      tools: sa.tools?.join(', ') || '',
      strategy_config: sa.strategy_config ? JSON.stringify(sa.strategy_config, null, 2) : '{}',
    })
  }

  const handleSave = async () => {
    if (!editingSA) return
    try {
      let strategyConfig = {}
      try { strategyConfig = JSON.parse(editForm.strategy_config || '{}') } catch { /* keep as string */ }
      const tools = (editForm.tools || '').split(',').map(t => t.trim()).filter(Boolean)
      await api.updateSubAgent(editingSA.name, {
        strategy: editForm.strategy,
        tools,
        system_prompt: editForm.system_prompt,
        strategy_config: strategyConfig,
        status: editingSA.status || 'active',
      })
      setEditingSA(null)
      load()
    } catch (err) {
      console.error(err)
    }
  }

  return (
    <>
      <div className="flex justify-end mb-3">
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button size="sm"><Plus size={14} className="mr-1" /> Add Sub-Agent</Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader><DialogTitle>Add Sub-Agent</DialogTitle></DialogHeader>
            <textarea
              value={yamlInput}
              onChange={e => setYamlInput(e.target.value)}
              placeholder="Paste sub-agent YAML configuration..."
              className="w-full h-64 rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
              <Button onClick={handleCreate}>Create</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <p className="text-muted-foreground text-sm">Loading...</p>
      ) : (
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Name</TableHead>
                <TableHead>Strategy</TableHead>
                <TableHead>Tools</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {subAgents.map(sa => {
                const isExpanded = expandedSA === sa.name
                return (
                  <>
                    <TableRow key={sa.name} className="cursor-pointer hover:bg-muted/30"
                      onClick={() => setExpandedSA(isExpanded ? null : sa.name)}>
                      <TableCell>
                        {isExpanded ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
                      </TableCell>
                      <TableCell className="font-medium font-mono text-sm">{sa.name}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{sa.strategy || '-'}</Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1 flex-wrap">
                          {sa.tools?.map(t => (
                            <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>
                          )) ?? <span className="text-muted-foreground">-</span>}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={sa.status === 'active' ? 'default' : 'secondary'}>
                          {sa.status || 'unknown'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="sm" onClick={e => { e.stopPropagation(); startEdit(sa) }}>
                            <Pencil size={14} />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={e => { e.stopPropagation(); handleDelete(sa.name) }}>
                            <Trash2 size={14} className="text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                    {isExpanded && (
                      <TableRow>
                        <TableCell colSpan={6} className="bg-muted/20 p-4">
                          <div className="space-y-3">
                            {sa.system_prompt && (
                              <div>
                                <div className="text-xs text-muted-foreground mb-1 font-medium">System Prompt</div>
                                <div className="text-sm whitespace-pre-wrap rounded-md border border-border bg-background p-3">{sa.system_prompt}</div>
                              </div>
                            )}
                            {sa.strategy_config && Object.keys(sa.strategy_config).length > 0 && (
                              <div>
                                <div className="text-xs text-muted-foreground mb-1 font-medium">Strategy Config</div>
                                <div className="rounded-md border border-border bg-background p-3">
                                  <pre className="text-xs font-mono">{JSON.stringify(sa.strategy_config, null, 2)}</pre>
                                </div>
                              </div>
                            )}
                            {sa.graph && Object.keys(sa.graph as object).length > 0 && (
                              <div>
                                <div className="text-xs text-muted-foreground mb-1 font-medium">
                                  Graph nodes: {String(Object.keys((sa.graph as Record<string,unknown>).nodes ?? {}).length)},
                                  edges: {String(((sa.graph as Record<string,unknown>).edges as Array<unknown>)?.length ?? 0)}
                                </div>
                                <div className="rounded-md border border-border bg-background p-3">
                                  <pre className="text-xs font-mono">{JSON.stringify(sa.graph, null, 2)}</pre>
                                </div>
                              </div>
                            )}
                            {!sa.system_prompt && (!sa.strategy_config || Object.keys(sa.strategy_config).length === 0) && (!sa.graph || Object.keys(sa.graph).length === 0) && (
                              <p className="text-sm text-muted-foreground">No additional details</p>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                )
              })}
              {subAgents.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                    No sub-agents registered
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Edit Sub-Agent Dialog */}
      <Dialog open={editingSA != null} onOpenChange={(open) => { if (!open) setEditingSA(null) }}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Edit {editingSA?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium">Strategy</label>
              <select
                value={editForm.strategy || 'react'}
                onChange={e => setEditForm(f => ({ ...f, strategy: e.target.value }))}
                className="w-full mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
              >
                <option value="react">react</option>
                <option value="function_calling">function_calling</option>
                <option value="dsl">dsl</option>
              </select>
            </div>
            <div>
              <label className="text-sm font-medium">Tools (comma-separated)</label>
              <Input value={editForm.tools || ''}
                onChange={e => setEditForm(f => ({ ...f, tools: e.target.value }))}
                className="mt-1 font-mono text-sm" placeholder="tool1, tool2" />
            </div>
            <div>
              <label className="text-sm font-medium">System Prompt</label>
              <textarea value={editForm.system_prompt || ''}
                onChange={e => setEditForm(f => ({ ...f, system_prompt: e.target.value }))}
                className="w-full h-40 rounded-md border border-input bg-background px-3 py-2 text-sm font-mono resize-none mt-1" />
            </div>
            <div>
              <label className="text-sm font-medium">Strategy Config (JSON)</label>
              <textarea value={editForm.strategy_config || '{}'}
                onChange={e => setEditForm(f => ({ ...f, strategy_config: e.target.value }))}
                className="w-full h-32 rounded-md border border-input bg-background px-3 py-2 text-xs font-mono resize-none mt-1" />
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="outline" onClick={() => setEditingSA(null)}>
              <X size={14} className="mr-1" /> Cancel
            </Button>
            <Button onClick={handleSave}>
              <Save size={14} className="mr-1" /> Save Changes
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

// ── Rate Limits tab ──

function RateLimitsTab() {
  const [config, setConfig] = useState<RateLimitConfig | null>(null)
  const [loading, setLoading] = useState(true)

  // Edit state
  const [editing, setEditing] = useState<'defaults' | 'agent' | 'tool' | null>(null)
  const [editKey, setEditKey] = useState('')
  const [editValues, setEditValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  const load = () => {
    setLoading(true)
    api.getRateLimits()
      .then(setConfig)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const startEdit = (type: 'defaults' | 'agent' | 'tool', key: string, values: Record<string, unknown>) => {
    setEditing(type)
    setEditKey(key)
    const str: Record<string, string> = {}
    for (const [k, v] of Object.entries(values)) {
      str[k] = String(v)
    }
    setEditValues(str)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const numeric: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(editValues)) {
        const n = Number(v)
        numeric[k] = isNaN(n) ? v : n
      }

      if (editing === 'agent') {
        await api.updateAgentRateLimit(editKey, { overrides: numeric })
      } else if (editing === 'tool') {
        await api.updateToolRateLimit(editKey, { overrides: numeric })
      } else if (editing === 'defaults') {
        // Defaults are updated via agent-level override with no agent_id
        // For now, save as global config
        await api.updateAgentRateLimit('__global__', { overrides: numeric })
      }
      setEditing(null)
      load()
    } catch (err) {
      console.error(err)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="text-muted-foreground text-sm">Loading...</p>
  if (!config) return <p className="text-muted-foreground text-sm">No rate limit configuration</p>

  return (
    <div className="space-y-4">
      {/* Defaults */}
      <Card className="p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium">Defaults</h3>
          <Button variant="ghost" size="sm"
            onClick={() => startEdit('defaults', '', config.defaults ?? {})}>
            <Pencil size={12} className="mr-1" /> Edit
          </Button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Object.entries(config.defaults ?? {}).map(([key, value]) => (
            <div key={key} className="rounded-md border border-border px-3 py-2">
              <div className="text-xs text-muted-foreground capitalize">{key.replace(/_/g, ' ')}</div>
              <div className="text-sm font-medium font-mono">{String(value)}</div>
            </div>
          ))}
          {Object.keys(config.defaults ?? {}).length === 0 && (
            <p className="text-sm text-muted-foreground col-span-full">No defaults configured</p>
          )}
        </div>
      </Card>

      {/* Agent Overrides */}
      <Card className="p-4">
        <h3 className="text-sm font-medium mb-3">Agent Overrides</h3>
        {Object.keys(config.agent_overrides ?? {}).length === 0 ? (
          <p className="text-sm text-muted-foreground">No agent-specific overrides</p>
        ) : (
          <div className="space-y-3">
            {Object.entries(config.agent_overrides ?? {}).map(([agentId, overrides]) => (
              <div key={agentId} className="rounded-md border border-border p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-mono font-medium">{agentId}</span>
                  <Button variant="ghost" size="sm"
                    onClick={() => startEdit('agent', agentId, overrides as Record<string, unknown>)}>
                    <Pencil size={12} className="mr-1" /> Edit
                  </Button>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {Object.entries(overrides as Record<string, unknown>).map(([key, value]) => (
                    <div key={key} className="text-xs">
                      <span className="text-muted-foreground">{key}: </span>
                      <span className="font-mono">{String(value)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Tool Overrides */}
      <Card className="p-4">
        <h3 className="text-sm font-medium mb-3">Tool Overrides</h3>
        {Object.keys(config.tool_overrides ?? {}).length === 0 ? (
          <p className="text-sm text-muted-foreground">No tool-specific overrides</p>
        ) : (
          <div className="space-y-3">
            {Object.entries(config.tool_overrides ?? {}).map(([toolName, overrides]) => (
              <div key={toolName} className="rounded-md border border-border p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-mono font-medium">{toolName}</span>
                  <Button variant="ghost" size="sm"
                    onClick={() => startEdit('tool', toolName, overrides as Record<string, unknown>)}>
                    <Pencil size={12} className="mr-1" /> Edit
                  </Button>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {Object.entries(overrides as Record<string, unknown>).map(([key, value]) => (
                    <div key={key} className="text-xs">
                      <span className="text-muted-foreground">{key}: </span>
                      <span className="font-mono">{String(value)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Edit Dialog */}
      <Dialog open={editing != null} onOpenChange={(open) => { if (!open) setEditing(null) }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {editing === 'defaults' ? 'Edit Defaults' :
               editing === 'agent' ? `Edit Agent Override: ${editKey}` :
               `Edit Tool Override: ${editKey}`}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {Object.entries(editValues).map(([key, value]) => (
              <div key={key}>
                <label className="text-sm font-medium capitalize">{key.replace(/_/g, ' ')}</label>
                <Input
                  value={value}
                  onChange={e => setEditValues(f => ({ ...f, [key]: e.target.value }))}
                  className="mt-1 font-mono text-sm"
                />
              </div>
            ))}
            {Object.keys(editValues).length === 0 && (
              <p className="text-sm text-muted-foreground">No fields to edit</p>
            )}
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="outline" onClick={() => setEditing(null)}>
              <X size={14} className="mr-1" /> Cancel
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              <Save size={14} className="mr-1" /> {saving ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function InfoField({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-md border border-border bg-background px-3 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-sm font-medium ${mono ? 'font-mono text-xs whitespace-pre-wrap' : ''}`}>{value}</div>
    </div>
  )
}
