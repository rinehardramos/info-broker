import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getCoreSettings, updateCoreSettings } from '../api/v3'
import { useForm } from 'react-hook-form'
import IconRail from '../components/layout/IconRail'

const CORE_FIELDS = [
  { key: 'db.postgres_url',        label: 'Postgres URL',         secret: false },
  { key: 'db.qdrant_host',         label: 'Qdrant Host',          secret: false },
  { key: 'rag.embedding_model',    label: 'Embedding Model',      secret: false },
  { key: 'llm.active_provider',    label: 'Active LLM Provider',  secret: false },
  { key: 'llm.openai.api_key',     label: 'OpenAI API Key',       secret: true },
  { key: 'llm.anthropic.api_key',  label: 'Anthropic API Key',    secret: true },
  { key: 'llm.gemini.api_key',     label: 'Gemini API Key',       secret: true },
  { key: 'llm.lmstudio.base_url',  label: 'LM Studio Base URL',   secret: false },
  { key: 'jwt.secret',             label: 'JWT Secret',           secret: true },
  { key: 'jwt.expiry_hours',       label: 'JWT Expiry (hours)',    secret: false },
]

function CoreSettingsForm() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['core-settings'], queryFn: getCoreSettings })
  const { register, handleSubmit } = useForm()

  const save = useMutation({
    mutationFn: (values: Record<string, string>) =>
      updateCoreSettings(
        CORE_FIELDS
          .filter(f => values[f.key] !== undefined && values[f.key] !== '')
          .map(f => ({ key: f.key, value: values[f.key], is_secret: f.secret }))
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['core-settings'] }),
  })

  return (
    <form onSubmit={handleSubmit(v => save.mutate(v as Record<string, string>))} className="flex flex-col gap-3">
      {CORE_FIELDS.map(f => (
        <div key={f.key} className="flex flex-col gap-1">
          <label className="text-[11px]" style={{ color: 'var(--subtext)' }}>{f.label}</label>
          <input
            type={f.secret ? 'password' : 'text'}
            placeholder={data?.settings[f.key] === null ? '••••••••' : (data?.settings[f.key] ?? '')}
            {...register(f.key)}
            className="px-2 py-1 rounded text-xs outline-none"
            style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }}
          />
        </div>
      ))}
      <button
        type="submit"
        disabled={save.isPending}
        className="mt-2 px-4 py-2 rounded text-xs font-semibold w-fit disabled:opacity-50"
        style={{ background: 'var(--accent)', color: 'var(--bg)', border: 'none', cursor: 'pointer' }}
      >
        {save.isPending ? 'Saving…' : 'Save Core Settings'}
      </button>
      {save.isSuccess && <span className="text-xs" style={{ color: '#4ade80' }}>Saved</span>}
    </form>
  )
}

export default function Settings() {
  const [section] = useState<'core'>('core')

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex h-full flex-1 overflow-hidden">
        <div className="w-40 flex-shrink-0 col-scroll py-3 px-2" style={{ background: 'var(--panel)', borderRight: '1px solid var(--border)' }}>
          <div className="text-[10px] font-semibold mb-2 px-1" style={{ color: 'var(--muted)' }}>SYSTEM</div>
          <button
            onClick={() => {}}
            className="w-full text-left px-2 py-1 rounded text-xs mb-1"
            style={{
              background: section === 'core' ? 'var(--panel2)' : 'transparent',
              color: section === 'core' ? 'var(--accent)' : 'var(--text)',
              border: 'none', cursor: 'pointer',
            }}
          >
            Core Settings
          </button>
        </div>

        <div className="flex-1 col-scroll p-4">
          <h2 className="text-sm font-bold mb-4 capitalize" style={{ color: 'var(--accent)' }}>
            Core Settings
          </h2>
          <CoreSettingsForm />
        </div>
      </div>
      <IconRail />
    </div>
  )
}
