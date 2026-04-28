import { useEffect } from 'react'
import { useForm, FormProvider } from 'react-hook-form'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getPluginSchema, getPluginConfig, savePluginConfig } from '../../api/v3'
import SchemaFormRenderer from './SchemaFormRenderer'

interface Props { pluginName: string }

export default function PluginConfigPage({ pluginName }: Props) {
  const qc = useQueryClient()
  const methods = useForm()

  const { data: schema } = useQuery({
    queryKey: ['plugin-schema', pluginName],
    queryFn: () => getPluginSchema(pluginName),
  })

  const { data: saved } = useQuery({
    queryKey: ['plugin-config', pluginName],
    queryFn: () => getPluginConfig(pluginName),
  })

  useEffect(() => {
    if (saved?.config) methods.reset(saved.config)
  }, [saved, methods])

  const save = useMutation({
    mutationFn: (data: Record<string, unknown>) => savePluginConfig(pluginName, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['plugin-config', pluginName] }),
  })

  return (
    <div className="p-4">
      <div className="text-sm font-semibold mb-3 capitalize" style={{ color: 'var(--accent)' }}>
        {pluginName} Plugin
      </div>

      {schema ? (
        <FormProvider {...methods}>
          <form onSubmit={methods.handleSubmit(data => save.mutate(data as Record<string, unknown>))}>
            <SchemaFormRenderer schema={schema} />
            <button
              type="submit"
              disabled={save.isPending}
              className="mt-4 px-4 py-2 rounded text-xs font-semibold disabled:opacity-50"
              style={{ background: 'var(--accent)', color: 'var(--bg)', border: 'none', cursor: 'pointer' }}
            >
              {save.isPending ? 'Saving…' : 'Save'}
            </button>
            {save.isSuccess && (
              <span className="ml-3 text-xs" style={{ color: '#4ade80' }}>Saved</span>
            )}
          </form>
        </FormProvider>
      ) : (
        <p className="text-xs" style={{ color: 'var(--muted)' }}>Loading schema…</p>
      )}
    </div>
  )
}
