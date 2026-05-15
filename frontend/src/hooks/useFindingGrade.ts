import { useState, useEffect, useCallback } from 'react'
import { api } from '../api/client'

interface MyGrade {
  grade: string
  note: string | null
  graded_at: string
}

interface GradeAggregate {
  a_count: number
  b_count: number
  c_count: number
  d_count: number
  total_graders: number
}

interface UseFindingGradeResult {
  myGrade: MyGrade | null
  aggregate: GradeAggregate | null
  isLoading: boolean
  isSaving: boolean
  save: (grade: string, note?: string) => Promise<void>
}

export function useFindingGrade(findingId: string, runId: string): UseFindingGradeResult {
  const [myGrade, setMyGrade] = useState<MyGrade | null>(null)
  const [aggregate, setAggregate] = useState<GradeAggregate | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)

  // Fetch current grade on mount (and when findingId changes)
  useEffect(() => {
    if (!findingId) return
    let cancelled = false
    setIsLoading(true)
    api
      .get<{ my_grade: MyGrade | null; aggregate: GradeAggregate }>(`/v3/findings/${findingId}/grade`)
      .then(({ data }) => {
        if (cancelled) return
        setMyGrade(data.my_grade)
        setAggregate(data.aggregate)
      })
      .catch(() => {
        // Non-fatal — grading UI degrades gracefully
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [findingId])

  const save = useCallback(
    async (grade: string, note?: string) => {
      setIsSaving(true)
      try {
        const { data } = await api.post<MyGrade>(`/v3/findings/${findingId}/grade`, {
          grade,
          note: note ?? null,
          run_id: runId,
        })
        setMyGrade({ grade: data.grade as string, note: (data as unknown as MyGrade).note, graded_at: (data as unknown as MyGrade).graded_at })
        // Refresh aggregate after save
        const { data: fresh } = await api.get<{ my_grade: MyGrade | null; aggregate: GradeAggregate }>(
          `/v3/findings/${findingId}/grade`,
        )
        setAggregate(fresh.aggregate)
        setMyGrade(fresh.my_grade)
      } finally {
        setIsSaving(false)
      }
    },
    [findingId, runId],
  )

  return { myGrade, aggregate, isLoading, isSaving, save }
}
