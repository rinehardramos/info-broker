import type { ReactNode } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface Props {
  title: string
  value: string | number
  sub?: ReactNode
  emphasis?: 'normal' | 'danger'
}

export function StatCard({ title, value, sub, emphasis = 'normal' }: Props) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-medium opacity-70 uppercase tracking-wide">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className={`text-2xl font-semibold tabular-nums ${emphasis === 'danger' ? 'text-red-500' : ''}`}>
          {value}
        </div>
        {sub && <div className="text-xs opacity-60 mt-1">{sub}</div>}
      </CardContent>
    </Card>
  )
}
