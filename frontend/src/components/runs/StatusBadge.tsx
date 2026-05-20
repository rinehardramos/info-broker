import { Badge } from '@/components/ui/badge'
import { Check, Loader2, X, Clock, HelpCircle } from 'lucide-react'

export type RunStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'awaiting_input'
  | 'ask_user'
  | 'budget_exhausted'

const VARIANT_MAP: Record<RunStatus, { variant: string; icon: React.ReactElement; className: string; label?: string }> = {
  queued:           { variant: 'queued',  icon: <Clock className="h-3 w-3" />,                className: 'bg-zinc-200 text-zinc-800' },
  running:          { variant: 'running', icon: <Loader2 className="h-3 w-3 animate-spin" />, className: 'bg-amber-200 text-amber-900' },
  succeeded:        { variant: 'success', icon: <Check className="h-3 w-3" />,                className: 'bg-green-200 text-green-900' },
  failed:           { variant: 'danger',  icon: <X className="h-3 w-3" />,                    className: 'bg-red-200 text-red-900' },
  cancelled:        { variant: 'muted',   icon: <X className="h-3 w-3" />,                    className: 'bg-zinc-200 text-zinc-700' },
  awaiting_input:   { variant: 'info',    icon: <HelpCircle className="h-3 w-3" />,           className: 'bg-blue-200 text-blue-900',   label: 'needs input' },
  ask_user:         { variant: 'info',    icon: <HelpCircle className="h-3 w-3" />,           className: 'bg-blue-200 text-blue-900',   label: 'needs input' },
  budget_exhausted: { variant: 'danger',  icon: <X className="h-3 w-3" />,                    className: 'bg-orange-200 text-orange-900', label: 'budget out' },
}

export function StatusBadge({ status }: { status: string }) {
  const key = (status as RunStatus) in VARIANT_MAP ? (status as RunStatus) : 'queued'
  const { variant, icon, className, label } = VARIANT_MAP[key]
  return (
    <Badge data-variant={variant} className={`inline-flex items-center gap-1 ${className}`}>
      {icon}
      <span>{label ?? key}</span>
    </Badge>
  )
}
