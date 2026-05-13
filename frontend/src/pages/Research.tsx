import { useQuery } from '@tanstack/react-query'
import IconRail from '../components/layout/IconRail'
import ThreeColumnLayout from '../components/layout/ThreeColumnLayout'
import ResultsPanel from '../components/results/ResultsPanel'
import AgentChat from '../components/agent/AgentChat'
import LiveStream from '../components/live/LiveStream'
import { getMe } from '../api/v3'
import { useSessionStore } from '../stores/sessionStore'

export default function Research() {
  const { setUser } = useSessionStore()

  useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      const user = await getMe()
      setUser(user.id, user.username, user.is_admin)
      return user
    },
  })

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <ThreeColumnLayout
        col1={<ResultsPanel />}
        col2={<AgentChat />}
        col3={<LiveStream />}
      />
      <IconRail />
    </div>
  )
}
