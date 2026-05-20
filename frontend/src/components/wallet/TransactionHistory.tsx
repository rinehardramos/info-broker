/**
 * TransactionHistory — paginated table of wallet_operations rows.
 */
import { useState } from 'react'
import { useWalletTransactions } from '@/hooks/useWallet'
import { Skeleton } from '@/components/ui/skeleton'

const PAGE_SIZE = 20

const OP_COLORS: Record<string, string> = {
  topup: '#34d399',
  hold: '#60a5fa',
  release: '#93c5fd',
  refund: '#34d399',
  extend_hold: '#f59e0b',
}

function opColor(op: string): string {
  if (op.startsWith('consume')) return '#f87171'
  return OP_COLORS[op] ?? 'var(--subtext)'
}

function opLabel(op: string): string {
  if (op.startsWith('consume_phase_')) {
    const n = op.replace('consume_phase_', '')
    return `consume p${n}`
  }
  return op
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function TransactionHistory() {
  const [page, setPage] = useState(0)
  const offset = page * PAGE_SIZE

  const { data, isLoading, isError } = useWalletTransactions(PAGE_SIZE, offset)
  const transactions = data?.transactions ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        padding: '20px 24px',
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>
        Transaction History
        {total > 0 && (
          <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--muted)', fontWeight: 400 }}>
            {total.toLocaleString()} total
          </span>
        )}
      </div>

      {isLoading && (
        <div className="py-3 space-y-1.5" aria-busy="true">
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-full" />
        </div>
      )}

      {isError && (
        <div style={{ fontSize: 12, color: '#f87171', padding: '12px 0' }}>
          Failed to load transactions
        </div>
      )}

      {!isLoading && !isError && transactions.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--muted)', padding: '12px 0' }}>
          No transactions yet
        </div>
      )}

      {transactions.length > 0 && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 110px 70px 90px',
              gap: '0 8px',
              fontSize: 11,
              color: 'var(--muted)',
              borderBottom: '1px solid var(--border)',
              paddingBottom: 6,
              marginBottom: 4,
            }}
          >
            <span>Time</span>
            <span>Operation</span>
            <span style={{ textAlign: 'right' }}>RU</span>
            <span style={{ textAlign: 'right' }}>Balance</span>
          </div>

          {transactions.map(txn => (
            <div
              key={txn.id}
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 110px 70px 90px',
                gap: '0 8px',
                fontSize: 12,
                padding: '5px 0',
                borderBottom: '1px solid rgba(255,255,255,0.04)',
                alignItems: 'center',
              }}
            >
              <span style={{ color: 'var(--subtext)', fontSize: 11 }}>{fmtDate(txn.created_at)}</span>
              <span style={{ color: opColor(txn.operation), fontFamily: 'monospace', fontSize: 11 }}>
                {opLabel(txn.operation)}
              </span>
              <span
                style={{
                  textAlign: 'right',
                  fontVariantNumeric: 'tabular-nums',
                  color: txn.operation.startsWith('consume') ? '#f87171' : '#34d399',
                }}
              >
                {txn.operation.startsWith('consume') ? '−' : '+'}
                {txn.amount_ru}
              </span>
              <span
                style={{
                  textAlign: 'right',
                  fontVariantNumeric: 'tabular-nums',
                  color: 'var(--text)',
                }}
              >
                {txn.balance_after.toLocaleString()}
              </span>
            </div>
          ))}

          {total > PAGE_SIZE && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12, fontSize: 12 }}>
              <button
                disabled={page === 0}
                onClick={() => setPage(p => Math.max(0, p - 1))}
                style={{
                  padding: '4px 10px',
                  borderRadius: 5,
                  border: '1px solid var(--border)',
                  background: 'transparent',
                  color: 'var(--subtext)',
                  cursor: page === 0 ? 'default' : 'pointer',
                  opacity: page === 0 ? 0.4 : 1,
                }}
              >
                Prev
              </button>
              <span style={{ color: 'var(--muted)' }}>
                {page + 1} / {totalPages}
              </span>
              <button
                disabled={page + 1 >= totalPages}
                onClick={() => setPage(p => p + 1)}
                style={{
                  padding: '4px 10px',
                  borderRadius: 5,
                  border: '1px solid var(--border)',
                  background: 'transparent',
                  color: 'var(--subtext)',
                  cursor: page + 1 >= totalPages ? 'default' : 'pointer',
                  opacity: page + 1 >= totalPages ? 0.4 : 1,
                }}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
