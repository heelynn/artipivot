import { useState, useEffect } from 'react'
import { api, type ToolInfo, type SubAgentInfo } from '@/lib/api'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight, Wrench, Bot } from 'lucide-react'

export function RuntimePage() {
  const { t } = useTranslation()

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl">
        <h1 className="text-2xl font-semibold mb-1">{t('runtime.title')}</h1>
        <p className="text-sm text-muted-foreground mb-6">
          {t('runtime.subtitle')}
        </p>

        <Tabs defaultValue="tools">
          <TabsList className="mb-4">
            <TabsTrigger value="tools">{t('runtime.tabs.tools')}</TabsTrigger>
            <TabsTrigger value="sub-agents">{t('runtime.tabs.subAgents')}</TabsTrigger>
          </TabsList>
          <TabsContent value="tools"><ToolsView /></TabsContent>
          <TabsContent value="sub-agents"><SubAgentsView /></TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

function ToolsView() {
  const { t } = useTranslation()
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    api.listRuntimeTools().then(setTools).catch(console.error).finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-muted-foreground text-sm">{t('runtime.loading')}</p>

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3">
        <Wrench size={16} />
        <h3 className="text-sm font-medium">{t('runtime.loadedTools', { count: tools.length })}</h3>
      </div>
      {tools.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('runtime.noTools')}</p>
      ) : (
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>{t('runtime.name')}</TableHead>
                <TableHead>{t('runtime.description')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tools.map(tool => {
                const isExpanded = expanded === tool.name
                return (
                  <>
                    <TableRow key={tool.name} className="cursor-pointer hover:bg-muted/30"
                      onClick={() => setExpanded(isExpanded ? null : tool.name)}>
                      <TableCell>
                        {isExpanded ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
                      </TableCell>
                      <TableCell className="font-mono text-sm">{tool.name}</TableCell>
                      <TableCell className="text-muted-foreground text-sm">{tool.description || '-'}</TableCell>
                    </TableRow>
                    {isExpanded && (
                      <TableRow>
                        <TableCell colSpan={3} className="bg-muted/20 p-4">
                          <div className="space-y-3">
                            <div>
                              <div className="text-xs text-muted-foreground mb-1 font-medium">{t('runtime.name')}</div>
                              <div className="text-sm font-mono">{tool.name}</div>
                            </div>
                            {tool.description && (
                              <div>
                                <div className="text-xs text-muted-foreground mb-1 font-medium">{t('runtime.description')}</div>
                                <div className="text-sm">{tool.description}</div>
                              </div>
                            )}
                            {tool.type && (
                              <div>
                                <div className="text-xs text-muted-foreground mb-1 font-medium">{t('runtime.type')}</div>
                                <Badge variant="outline">{tool.type}</Badge>
                              </div>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </Card>
  )
}

function SubAgentsView() {
  const { t } = useTranslation()
  const [subAgents, setSubAgents] = useState<SubAgentInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    api.listRuntimeSubAgents().then(setSubAgents).catch(console.error).finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-muted-foreground text-sm">{t('runtime.loading')}</p>

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3">
        <Bot size={16} />
        <h3 className="text-sm font-medium">{t('runtime.loadedSubAgents', { count: subAgents.length })}</h3>
      </div>
      {subAgents.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('runtime.noSubAgents')}</p>
      ) : (
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>{t('runtime.name')}</TableHead>
                <TableHead>{t('runtime.strategy')}</TableHead>
                <TableHead>{t('runtime.tools')}</TableHead>
                <TableHead>{t('runtime.systemPrompt')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {subAgents.map(sa => {
                const isExpanded = expanded === sa.name
                return (
                  <>
                    <TableRow key={sa.name} className="cursor-pointer hover:bg-muted/30"
                      onClick={() => setExpanded(isExpanded ? null : sa.name)}>
                      <TableCell>
                        {isExpanded ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
                      </TableCell>
                      <TableCell className="font-mono text-sm">{sa.name}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{sa.strategy || '-'}</Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1 flex-wrap">
                          {sa.tools?.map(t => <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>) ?? '-'}
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm max-w-xs truncate">
                        {sa.system_prompt || '-'}
                      </TableCell>
                    </TableRow>
                    {isExpanded && (
                      <TableRow>
                        <TableCell colSpan={5} className="bg-muted/20 p-4">
                          <div className="space-y-3">
                            <div className="grid grid-cols-2 gap-3">
                              <div>
                                <div className="text-xs text-muted-foreground mb-1 font-medium">{t('runtime.name')}</div>
                                <div className="text-sm font-mono">{sa.name}</div>
                              </div>
                              <div>
                                <div className="text-xs text-muted-foreground mb-1 font-medium">{t('runtime.strategy')}</div>
                                <Badge variant="outline">{sa.strategy || '-'}</Badge>
                              </div>
                            </div>
                            {sa.tools && sa.tools.length > 0 && (
                              <div>
                                <div className="text-xs text-muted-foreground mb-1 font-medium">{t('runtime.tools')}</div>
                                <div className="flex gap-1 flex-wrap">
                                  {sa.tools.map(t => <Badge key={t} variant="secondary">{t}</Badge>)}
                                </div>
                              </div>
                            )}
                            {sa.system_prompt && (
                              <div>
                                <div className="text-xs text-muted-foreground mb-1 font-medium">{t('runtime.systemPrompt')}</div>
                                <div className="text-sm whitespace-pre-wrap rounded-md border border-border bg-background p-3">
                                  {sa.system_prompt}
                                </div>
                              </div>
                            )}
                            {sa.strategy_config && Object.keys(sa.strategy_config).length > 0 && (
                              <div>
                                <div className="text-xs text-muted-foreground mb-1 font-medium">{t('runtime.strategyConfig')}</div>
                                <pre className="text-xs font-mono rounded-md border border-border bg-background p-3">
                                  {JSON.stringify(sa.strategy_config, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </Card>
  )
}
