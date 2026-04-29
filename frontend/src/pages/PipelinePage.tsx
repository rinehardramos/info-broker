import { useParams } from 'react-router-dom'
import { PipelineBuilder } from '../components/pipeline/PipelineBuilder'
import IconRail from '../components/layout/IconRail'

export default function PipelinePage() {
  const { id } = useParams<{ id: string }>()

  return (
    <div className="flex h-screen" style={{ background: 'var(--bg)', color: 'var(--text)' }}>
      <div className="flex-1 overflow-hidden">
        <PipelineBuilder initialPipelineId={id} />
      </div>
      <IconRail />
    </div>
  )
}
