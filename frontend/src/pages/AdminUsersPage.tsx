import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listUsers, patchUser, UserRecord, UserRole } from '../api/v3'
import IconRail from '../components/layout/IconRail'
import { useSessionStore } from '../stores/sessionStore'

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      style={{
        width: 34,
        height: 18,
        borderRadius: 9,
        background: checked ? 'var(--accent)' : 'var(--border)',
        border: 'none',
        cursor: disabled ? 'not-allowed' : 'pointer',
        position: 'relative',
        opacity: disabled ? 0.5 : 1,
        flexShrink: 0,
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: 2,
          left: checked ? 18 : 2,
          width: 14,
          height: 14,
          borderRadius: '50%',
          background: 'var(--bg)',
          transition: 'left 0.15s',
        }}
      />
    </button>
  )
}

const PAGE_SIZE_OPTIONS = [25, 50, 100] as const

export default function AdminUsersPage() {
  const qc = useQueryClient()
  const { userId } = useSessionStore()

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-users', page, pageSize, search],
    queryFn: () => listUsers(page, pageSize, search || undefined),
  })

  const users: UserRecord[] = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 1

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<Pick<UserRecord, 'is_admin' | 'is_active' | 'role'>> }) =>
      patchUser(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  })

  const handleSearch = useCallback(() => {
    setPage(1)
    setSearch(searchInput.trim())
  }, [searchInput])

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSearch()
  }

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize)
    setPage(1)
  }

  const adminCount = users.filter(u => u.is_admin).length

  return (
    <div
      className="flex"
      style={{ height: '100vh', background: 'var(--bg)', color: 'var(--text)' }}
    >
      <div className="flex flex-col flex-1 overflow-hidden">
        {/* Header */}
        <div
          className="flex items-center gap-4 px-6 py-4 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--border)', background: 'var(--panel)' }}
        >
          <span style={{ color: 'var(--accent)', fontSize: 16 }}>◫</span>
          <div>
            <h1 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', margin: 0 }}>
              User Management
            </h1>
            <p style={{ fontSize: 11, color: 'var(--subtext)', margin: 0 }}>
              {total} {total === 1 ? 'user' : 'users'} total — {adminCount} admin{adminCount !== 1 ? 's' : ''} on this page
            </p>
          </div>

          {/* Search */}
          <div className="flex items-center gap-2" style={{ marginLeft: 'auto' }}>
            <input
              type="text"
              placeholder="Search username or email…"
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              style={{
                background: 'var(--panel)',
                color: 'var(--text)',
                border: '1px solid var(--border)',
                borderRadius: 4,
                fontSize: 12,
                padding: '4px 8px',
                width: 220,
              }}
            />
            <button
              onClick={handleSearch}
              style={{
                background: 'var(--accent)',
                color: 'var(--bg)',
                border: 'none',
                borderRadius: 4,
                fontSize: 12,
                padding: '4px 10px',
                cursor: 'pointer',
              }}
            >
              Search
            </button>
            {search && (
              <button
                onClick={() => { setSearchInput(''); setSearch(''); setPage(1) }}
                style={{
                  background: 'transparent',
                  color: 'var(--subtext)',
                  border: '1px solid var(--border)',
                  borderRadius: 4,
                  fontSize: 12,
                  padding: '4px 8px',
                  cursor: 'pointer',
                }}
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-6" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {isLoading && (
            <p style={{ color: 'var(--muted)', fontSize: 12 }}>Loading users…</p>
          )}

          {error && (
            <p style={{ color: '#f87171', fontSize: 12 }}>
              Failed to load users. Are you an admin?
            </p>
          )}

          {!isLoading && !error && users.length === 0 && (
            <p style={{ color: 'var(--muted)', fontSize: 12 }}>
              {search ? `No users matching "${search}".` : 'No users found.'}
            </p>
          )}

          {!isLoading && !error && users.length > 0 && (
            <div style={{ overflowX: 'auto' }}>
              <table
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: 12,
                }}
              >
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['Username', 'Email', 'Org', 'Role', 'Admin', 'Active', 'Created'].map(h => (
                      <th
                        key={h}
                        style={{
                          padding: '6px 12px',
                          textAlign: 'left',
                          color: 'var(--subtext)',
                          fontWeight: 500,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {users.map(user => {
                    const isSelf = user.id === userId
                    return (
                      <tr
                        key={user.id}
                        style={{
                          borderBottom: '1px solid var(--border)',
                          background: isSelf ? 'var(--panel2)' : 'transparent',
                        }}
                      >
                        <td style={{ padding: '8px 12px', color: 'var(--text)', fontWeight: isSelf ? 600 : 400 }}>
                          {user.username}
                          {isSelf && (
                            <span
                              style={{
                                marginLeft: 6,
                                fontSize: 10,
                                color: 'var(--accent)',
                                background: 'var(--panel)',
                                padding: '1px 5px',
                                borderRadius: 3,
                              }}
                            >
                              you
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '8px 12px', color: 'var(--subtext)' }}>
                          {user.email ?? '—'}
                        </td>
                        <td style={{ padding: '8px 12px', color: 'var(--subtext)', fontFamily: 'monospace', fontSize: 11 }}>
                          {user.org_id ? user.org_id.slice(0, 8) + '…' : '—'}
                        </td>
                        <td style={{ padding: '8px 12px' }}>
                          <select
                            value={user.role ?? 'analyst'}
                            disabled={isSelf}
                            onChange={e => patch.mutate({ id: user.id, body: { role: e.target.value as UserRole } })}
                            style={{
                              background: 'var(--panel)',
                              color: 'var(--text)',
                              border: '1px solid var(--border)',
                              borderRadius: 4,
                              fontSize: 11,
                              padding: '2px 6px',
                              cursor: isSelf ? 'not-allowed' : 'pointer',
                              opacity: isSelf ? 0.5 : 1,
                            }}
                          >
                            <option value="admin">admin</option>
                            <option value="analyst">analyst</option>
                            <option value="viewer">viewer</option>
                          </select>
                        </td>
                        <td style={{ padding: '8px 12px' }}>
                          <Toggle
                            checked={user.is_admin}
                            disabled={isSelf}
                            onChange={v => patch.mutate({ id: user.id, body: { is_admin: v } })}
                          />
                        </td>
                        <td style={{ padding: '8px 12px' }}>
                          <Toggle
                            checked={user.is_active}
                            disabled={isSelf}
                            onChange={v => patch.mutate({ id: user.id, body: { is_active: v } })}
                          />
                        </td>
                        <td style={{ padding: '8px 12px', color: 'var(--muted)', fontSize: 11, whiteSpace: 'nowrap' }}>
                          {new Date(user.created_at).toLocaleDateString()}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination controls */}
          {!isLoading && !error && total > 0 && (
            <div
              className="flex items-center gap-3"
              style={{ marginTop: 'auto', paddingTop: 8, flexWrap: 'wrap' }}
            >
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                style={{
                  background: 'var(--panel)',
                  color: 'var(--text)',
                  border: '1px solid var(--border)',
                  borderRadius: 4,
                  fontSize: 12,
                  padding: '4px 10px',
                  cursor: page <= 1 ? 'not-allowed' : 'pointer',
                  opacity: page <= 1 ? 0.4 : 1,
                }}
              >
                Previous
              </button>

              <span style={{ fontSize: 12, color: 'var(--subtext)' }}>
                Page {page} of {totalPages}
              </span>

              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                style={{
                  background: 'var(--panel)',
                  color: 'var(--text)',
                  border: '1px solid var(--border)',
                  borderRadius: 4,
                  fontSize: 12,
                  padding: '4px 10px',
                  cursor: page >= totalPages ? 'not-allowed' : 'pointer',
                  opacity: page >= totalPages ? 0.4 : 1,
                }}
              >
                Next
              </button>

              <span style={{ fontSize: 12, color: 'var(--muted)', marginLeft: 4 }}>
                {total} total
              </span>

              {/* Page size selector */}
              <div className="flex items-center gap-1" style={{ marginLeft: 'auto' }}>
                <span style={{ fontSize: 12, color: 'var(--subtext)' }}>Per page:</span>
                {PAGE_SIZE_OPTIONS.map(s => (
                  <button
                    key={s}
                    onClick={() => handlePageSizeChange(s)}
                    style={{
                      background: pageSize === s ? 'var(--accent)' : 'var(--panel)',
                      color: pageSize === s ? 'var(--bg)' : 'var(--text)',
                      border: '1px solid var(--border)',
                      borderRadius: 4,
                      fontSize: 11,
                      padding: '3px 8px',
                      cursor: 'pointer',
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <IconRail />
    </div>
  )
}
