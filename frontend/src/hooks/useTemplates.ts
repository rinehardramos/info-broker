/**
 * useTemplates — Enhancement 3.2
 *
 * Wraps the 5 saved-template endpoints + the 2 per-user-defaults endpoints.
 */
import { useState, useCallback, useEffect } from 'react'
import { api } from '../api/client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TemplateEnvelope {
  speed: string
  capability: string
  resource: string
  depth: string
  hypothesis_count: string
  mode: string | null
}

export interface Template {
  id: string
  user_id: string
  name: string
  query: string
  envelope: TemplateEnvelope
  strategy_id: string
  last_used: string | null
  use_count: number
  created_at: string
}

export interface TemplateCreateIn {
  name: string
  query: string
  envelope: Partial<TemplateEnvelope>
  strategy_id: string
}

export interface UserDefaults {
  envelope: Partial<TemplateEnvelope>
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useTemplates() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [defaults, setDefaults] = useState<UserDefaults | null>(null)
  const [defaultsLoading, setDefaultsLoading] = useState(false)

  // -------------------------------------------------------------------------
  // List templates
  // -------------------------------------------------------------------------

  const fetchTemplates = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const { data } = await api.get<Template[]>('/v3/templates')
      setTemplates(data)
    } catch {
      setError('Failed to load templates')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchTemplates()
  }, [fetchTemplates])

  // -------------------------------------------------------------------------
  // Create / upsert template
  // -------------------------------------------------------------------------

  const createTemplate = useCallback(async (input: TemplateCreateIn): Promise<Template | null> => {
    try {
      const { data } = await api.post<Template>('/v3/templates', input)
      setTemplates(prev => {
        const filtered = prev.filter(t => t.name !== data.name)
        return [data, ...filtered]
      })
      return data
    } catch {
      setError('Failed to save template')
      return null
    }
  }, [])

  // -------------------------------------------------------------------------
  // Delete template
  // -------------------------------------------------------------------------

  const deleteTemplate = useCallback(async (templateId: string): Promise<boolean> => {
    try {
      await api.delete(`/v3/templates/${templateId}`)
      setTemplates(prev => prev.filter(t => t.id !== templateId))
      return true
    } catch {
      setError('Failed to delete template')
      return false
    }
  }, [])

  // -------------------------------------------------------------------------
  // Use template (bump last_used + use_count)
  // -------------------------------------------------------------------------

  const useTemplate = useCallback(async (templateId: string): Promise<Template | null> => {
    try {
      const { data } = await api.post<Template>(`/v3/templates/${templateId}/use`)
      setTemplates(prev =>
        prev.map(t => (t.id === templateId ? data : t))
          .sort((a, b) => {
            if (a.last_used && b.last_used) return b.last_used.localeCompare(a.last_used)
            if (a.last_used) return -1
            if (b.last_used) return 1
            return b.created_at.localeCompare(a.created_at)
          })
      )
      return data
    } catch {
      setError('Failed to record template usage')
      return null
    }
  }, [])

  // -------------------------------------------------------------------------
  // User defaults — GET
  // -------------------------------------------------------------------------

  const fetchDefaults = useCallback(async () => {
    setDefaultsLoading(true)
    try {
      const { data } = await api.get<UserDefaults>('/v3/user/defaults')
      setDefaults(data)
    } catch {
      // Non-fatal; fall back to hardcoded defaults
    } finally {
      setDefaultsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDefaults()
  }, [fetchDefaults])

  // -------------------------------------------------------------------------
  // User defaults — PUT
  // -------------------------------------------------------------------------

  const saveDefaults = useCallback(async (envelope: Partial<TemplateEnvelope>): Promise<boolean> => {
    try {
      const { data } = await api.put<UserDefaults>('/v3/user/defaults', { envelope })
      setDefaults(data)
      return true
    } catch {
      setError('Failed to save defaults')
      return false
    }
  }, [])

  return {
    templates,
    isLoading,
    error,
    fetchTemplates,
    createTemplate,
    deleteTemplate,
    useTemplate,
    defaults,
    defaultsLoading,
    saveDefaults,
  }
}
