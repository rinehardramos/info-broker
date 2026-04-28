export default function AgentChat() {
  return (
    <div className="p-4">
      <input
        placeholder="Ask the agent…"
        className="w-full text-xs bg-transparent outline-none"
        style={{ color: 'var(--text)', borderBottom: '1px solid var(--border)', paddingBottom: 4 }}
        readOnly
      />
    </div>
  )
}
