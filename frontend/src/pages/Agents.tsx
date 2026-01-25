import { useState, useEffect } from 'react'
import { Play, Power, Clock, Cpu, Bot } from 'lucide-react'
import { fetchAPI } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

interface AgentConfig {
  id: number
  name: string
  display_name: string
  description: string
  enabled: boolean
  schedule: string
  ai_model: string
  ai_base_url: string
  config: Record<string, unknown>
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState<string | null>(null)

  const load = async () => {
    try {
      const data = await fetchAPI<AgentConfig[]>('/agents')
      setAgents(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const toggleAgent = async (agent: AgentConfig) => {
    await fetchAPI(`/agents/${agent.name}`, {
      method: 'PUT',
      body: JSON.stringify({ enabled: !agent.enabled }),
    })
    load()
  }

  const triggerAgent = async (name: string) => {
    setTriggering(name)
    try {
      await fetchAPI(`/agents/${name}/trigger`, { method: 'POST' })
      alert('Agent 已触发')
    } catch (e) {
      alert('触发失败')
    } finally {
      setTriggering(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <span className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-[22px] font-bold text-foreground tracking-tight">Agent</h1>
        <p className="text-[13px] text-muted-foreground mt-1">自动化任务管理与调度</p>
      </div>

      {agents.length === 0 ? (
        <div className="card flex flex-col items-center justify-center py-20">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary/10 to-[hsl(260,70%,55%)]/10 flex items-center justify-center mb-4">
            <Bot className="w-6 h-6 text-primary" />
          </div>
          <p className="text-[15px] font-semibold text-foreground">暂无 Agent</p>
          <p className="text-[13px] text-muted-foreground mt-1.5">启动后台服务后 Agent 会自动注册</p>
        </div>
      ) : (
        <div className="space-y-4">
          {agents.map(agent => (
            <div
              key={agent.name}
              className="card-hover p-6"
            >
              <div className="flex items-start justify-between gap-6">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3">
                    <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${agent.enabled ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]' : 'bg-border'}`} />
                    <h3 className="text-[15px] font-semibold text-foreground">{agent.display_name}</h3>
                  </div>
                  <p className="text-[13px] text-muted-foreground mt-2.5 ml-[22px] leading-relaxed">{agent.description}</p>
                  <div className="flex items-center gap-2.5 mt-3.5 ml-[22px]">
                    {agent.schedule && (
                      <Badge variant="secondary">
                        <Clock className="w-3 h-3" />
                        {agent.schedule}
                      </Badge>
                    )}
                    {agent.ai_model && (
                      <Badge variant="secondary">
                        <Cpu className="w-3 h-3" />
                        {agent.ai_model}
                      </Badge>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => triggerAgent(agent.name)}
                    disabled={!agent.enabled || triggering === agent.name}
                  >
                    {triggering === agent.name ? (
                      <span className="w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin" />
                    ) : (
                      <Play className="w-3.5 h-3.5" />
                    )}
                    {triggering === agent.name ? '运行中' : '触发'}
                  </Button>
                  <Button
                    variant={agent.enabled ? 'destructive' : 'default'}
                    size="sm"
                    onClick={() => toggleAgent(agent)}
                  >
                    <Power className="w-3.5 h-3.5" />
                    {agent.enabled ? '停用' : '启用'}
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
