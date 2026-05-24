import { useQuery } from '@tanstack/react-query'
import { getNodeHealth, NodeHealthOut } from '../../api/v3'
import { useSessionStore } from '../../stores/sessionStore'

/**
 * Admin-only "Action needed" panel.
 * Surfaces every tool/node that is unhealthy OR requires an API key.
 * Links into the existing "Core Settings" tab for key configuration.
 */

interface AdminActionItemsProps {
  /** Called when the user clicks "Configure" on an item — used to navigate to Core Settings. */
  onNavigateToCoreSettings: () => void
}

export default function AdminActionItems({ onNavigateToCoreSettings }: AdminActionItemsProps) {
  const isAdmin = useSessionStore(s => s.isAdmin)

  const { data: nodes = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['nodeHealth'],
    queryFn: getNodeHealth,
    enabled: isAdmin,
  })

  if (!isAdmin) return null

  if (isLoading) {
    return (
      <div
        className="rounded p-3"
        style={{ background: 'var(--panel)', border: '1px solid var(--border)' }}
      >
        <p className="text-xs" style={{ color: 'var(--muted)' }}>Checking tool health…</p>
      </div>
    )
  }

  if (isError) {
    return (
      <div
        className="rounded p-3 flex flex-col gap-2"
        style={{ background: 'var(--panel)', border: '1px solid var(--border)' }}
      >
        <p className="text-xs" style={{ color: '#f87171' }}>Failed to load tool health status</p>
        <button
          onClick={() => refetch()}
          className="px-3 py-1 rounded text-xs w-fit"
          style={{
            background: 'var(--panel)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
            cursor: 'pointer',
          }}
        >
          Retry
        </button>
      </div>
    )
  }

  const actionItems: NodeHealthOut[] = nodes.filter(n => !n.healthy || n.requires_key)

  return (
    <div
      data-testid="admin-action-items"
      className="rounded flex flex-col gap-3 p-3"
      style={{
        background: 'var(--panel)',
        border: actionItems.length > 0 ? '1px solid #ef444433' : '1px solid var(--border)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold" style={{ color: 'var(--text)' }}>
            Action needed
          </span>
          {actionItems.length > 0 && (
            <span
              className="text-[10px] font-semibold px-2 py-0.5 rounded"
              data-testid="action-items-badge"
              style={{ background: '#ef444422', color: '#f87171', border: '1px solid #ef444433' }}
            >
              {actionItems.length}
            </span>
          )}
        </div>
        <button
          onClick={() => refetch()}
          className="text-[10px] px-2 py-1 rounded"
          style={{
            background: 'transparent',
            color: 'var(--muted)',
            border: '1px solid var(--border)',
            cursor: 'pointer',
          }}
        >
          Refresh
        </button>
      </div>

      {/* Empty state */}
      {actionItems.length === 0 && (
        <div className="flex items-center gap-2" data-testid="all-healthy-state">
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: '#4ade80',
              flexShrink: 0,
              display: 'inline-block',
            }}
          />
          <span className="text-xs" style={{ color: '#4ade80' }}>
            All tools healthy — no action required
          </span>
        </div>
      )}

      {/* Action item list */}
      {actionItems.length > 0 && (
        <div className="flex flex-col gap-2">
          {actionItems.map(node => (
            <div
              key={node.node_type}
              data-testid={`action-item-${node.node_type}`}
              className="rounded p-3 flex flex-col gap-2"
              style={{
                background: 'var(--bg, #0f0f0f)',
                border: '1px solid #ef444433',
              }}
            >
              {/* Title row */}
              <div className="flex items-center gap-2">
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    background: '#f87171',
                    flexShrink: 0,
                    display: 'inline-block',
                  }}
                />
                <span className="flex-1 text-xs font-medium" style={{ color: 'var(--text)' }}>
                  {node.display_name}
                </span>
                {!node.healthy && (
                  <span
                    className="text-[10px] px-2 py-0.5 rounded"
                    style={{ background: '#ef444422', color: '#f87171', border: '1px solid #ef444433' }}
                  >
                    Unhealthy
                  </span>
                )}
              </div>

              {/* Error / requires_key message */}
              {node.error && (
                <p
                  className="text-[11px]"
                  data-testid={`action-item-error-${node.node_type}`}
                  style={{ color: '#f87171' }}
                >
                  {node.error}
                </p>
              )}

              {node.requires_key && (
                <p
                  className="text-[11px]"
                  data-testid={`action-item-requires-key-${node.node_type}`}
                  style={{ color: 'var(--subtext)' }}
                >
                  Requires API key: <code style={{ color: 'var(--text)' }}>{node.requires_key}</code>
                </p>
              )}

              {/* Setup instructions */}
              {node.setup_instructions && (
                <p
                  className="text-[11px]"
                  style={{ color: 'var(--subtext)', lineHeight: 1.5, whiteSpace: 'pre-line' }}
                >
                  {node.setup_instructions}
                </p>
              )}

              {/* Action links */}
              <div className="flex items-center gap-3 flex-wrap">
                {node.setup_url && !node.setup_url.startsWith('/') && (
                  <a
                    href={node.setup_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px]"
                    data-testid={`action-item-setup-url-${node.node_type}`}
                    style={{ color: 'var(--accent)' }}
                  >
                    Get API key →
                  </a>
                )}

                <button
                  onClick={onNavigateToCoreSettings}
                  className="text-[11px] px-3 py-1 rounded"
                  data-testid={`action-item-configure-${node.node_type}`}
                  style={{
                    background: 'var(--panel)',
                    color: 'var(--text)',
                    border: '1px solid var(--border)',
                    cursor: 'pointer',
                  }}
                >
                  Configure in Core Settings
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
