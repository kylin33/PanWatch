import { useState, useEffect } from 'react'
import { Check, Eye, EyeOff } from 'lucide-react'
import { fetchAPI } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'

interface Setting {
  key: string
  value: string
  description: string
}

const SENSITIVE_KEYS = ['ai_api_key', 'notify_telegram_bot_token']

export default function SettingsPage() {
  const [settings, setSettings] = useState<Setting[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const [edited, setEdited] = useState<Record<string, string>>({})
  const [visible, setVisible] = useState<Record<string, boolean>>({})

  const load = async () => {
    try {
      const data = await fetchAPI<Setting[]>('/settings')
      setSettings(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleSave = async (key: string) => {
    setSaving(key)
    try {
      await fetchAPI(`/settings/${key}`, {
        method: 'PUT',
        body: JSON.stringify({ value: edited[key] ?? settings.find(s => s.key === key)?.value }),
      })
      const newEdited = { ...edited }
      delete newEdited[key]
      setEdited(newEdited)
      setSaved(key)
      setTimeout(() => setSaved(null), 2000)
      load()
    } catch (e) {
      alert('保存失败')
    } finally {
      setSaving(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <span className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    )
  }

  const groups = {
    'AI 模型': settings.filter(s => s.key.startsWith('ai_')),
    '通知': settings.filter(s => s.key.startsWith('notify_')),
    '网络': settings.filter(s => ['http_proxy'].includes(s.key)),
    '调度': settings.filter(s => s.key.includes('cron')),
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-[22px] font-bold text-foreground tracking-tight">设置</h1>
        <p className="text-[13px] text-muted-foreground mt-1">系统配置与密钥管理</p>
      </div>

      <div className="space-y-6">
        {Object.entries(groups).map(([group, items]) => (
          items.length > 0 && (
            <section key={group} className="card p-6">
              <h3 className="text-[13px] font-semibold text-foreground mb-5">{group}</h3>
              <div className="space-y-5">
                {items.map(setting => {
                  const currentValue = edited[setting.key] ?? setting.value
                  const isChanged = setting.key in edited
                  const isSensitive = SENSITIVE_KEYS.includes(setting.key)

                  return (
                    <div key={setting.key}>
                      <Label>{setting.description || setting.key}</Label>
                      <div className="flex items-center gap-2.5">
                        <div className="relative flex-1">
                          <Input
                            type={isSensitive && !visible[setting.key] ? 'password' : 'text'}
                            value={currentValue}
                            onChange={e => setEdited({ ...edited, [setting.key]: e.target.value })}
                            className={`font-mono ${isSensitive ? 'pr-10' : ''} ${isChanged ? 'ring-2 ring-primary/20 border-primary/30' : ''}`}
                            placeholder={setting.key}
                          />
                          {isSensitive && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8"
                              onClick={() => setVisible({ ...visible, [setting.key]: !visible[setting.key] })}
                            >
                              {visible[setting.key] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </Button>
                          )}
                        </div>
                        <button
                          onClick={() => handleSave(setting.key)}
                          disabled={!isChanged || saving === setting.key}
                          className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all ${
                            saved === setting.key
                              ? 'bg-emerald-500/10 text-emerald-600'
                              : isChanged
                                ? 'bg-gradient-to-r from-primary to-[hsl(260,70%,55%)] text-white shadow-[0_2px_8px_rgba(79,70,229,0.3)]'
                                : 'text-muted-foreground/30'
                          }`}
                        >
                          {saving === setting.key ? (
                            <span className="w-4 h-4 border-2 border-current/30 border-t-current rounded-full animate-spin" />
                          ) : (
                            <Check className="w-4 h-4" />
                          )}
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          )
        ))}
      </div>
    </div>
  )
}
