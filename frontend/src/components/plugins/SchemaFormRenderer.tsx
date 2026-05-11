import { useFormContext } from 'react-hook-form'

interface JSONSchemaProperty {
  type: string
  title?: string
  default?: unknown
  minimum?: number
  maximum?: number
  enum?: string[]
  description?: string
}

interface SchemaObject {
  type: string
  properties?: Record<string, JSONSchemaProperty>
}

interface Props {
  schema: Record<string, unknown>
}

const inputStyle = {
  background: 'var(--panel)',
  color: 'var(--text)',
  border: '1px solid var(--border)',
}

export default function SchemaFormRenderer({ schema }: Props) {
  const { register } = useFormContext()
  const s = schema as unknown as SchemaObject

  if (!s.properties) {
    return <p className="text-xs" style={{ color: 'var(--muted)' }}>No configuration options.</p>
  }

  return (
    <div className="flex flex-col gap-3">
      {Object.entries(s.properties).map(([key, prop]) => {
        const id = `field-${key}`
        return (
          <div key={key} className="flex flex-col gap-1">
            <label htmlFor={id} className="text-[11px]" style={{ color: 'var(--subtext)' }}>
              {prop.title ?? key}
            </label>

            {prop.enum ? (
              <select
                id={id}
                {...register(key)}
                defaultValue={String(prop.default ?? '')}
                className="px-2 py-1 rounded text-xs outline-none"
                style={inputStyle}
              >
                {prop.enum.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            ) : prop.type === 'boolean' ? (
              <input
                id={id}
                type="checkbox"
                {...register(key)}
                defaultChecked={Boolean(prop.default)}
                className="w-4 h-4"
              />
            ) : (
              <input
                id={id}
                type={prop.type === 'integer' || prop.type === 'number' ? 'number' : 'text'}
                {...register(key)}
                defaultValue={String(prop.default ?? '')}
                min={prop.minimum}
                max={prop.maximum}
                className="px-2 py-1 rounded text-xs outline-none"
                style={inputStyle}
              />
            )}

            {prop.description && (
              <span className="text-[10px]" style={{ color: 'var(--muted)' }}>{prop.description}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}
