import IconRail from '../components/layout/IconRail'

export default function Settings() {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 p-4">
        <h2 className="text-sm font-bold" style={{ color: 'var(--accent)' }}>Settings</h2>
      </div>
      <IconRail />
    </div>
  )
}
