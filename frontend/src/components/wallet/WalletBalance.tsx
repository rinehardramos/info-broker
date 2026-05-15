/**
 * WalletBalance — large balance display with held/spendable/lifetime breakdown.
 */
import type { WalletSnapshot } from '@/api/v3'

interface Props {
  wallet: WalletSnapshot
}

export function WalletBalance({ wallet }: Props) {
  const { balance_ru, held_ru, available_ru, floor_ru, spent_ru_lifetime } = wallet
  const spendable = Math.max(0, available_ru - floor_ru)

  return (
    <div
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        padding: '20px 24px',
        minWidth: 260,
      }}
    >
      <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 4 }}>Available</div>
      <div style={{ fontSize: 36, fontWeight: 700, color: '#a78bfa', lineHeight: 1.1 }}>
        {available_ru.toLocaleString()}
        <span style={{ fontSize: 16, color: 'var(--muted)', marginLeft: 4, fontWeight: 400 }}>RU</span>
      </div>

      <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <Row label="Total balance" value={`${balance_ru.toLocaleString()} RU`} />
        <Row label="Held (in-flight)" value={`${held_ru.toLocaleString()} RU`} dimmed />
        <Row label="Spendable (above floor)" value={`${spendable.toLocaleString()} RU`} accent />
        <div style={{ height: 1, background: 'var(--border)', margin: '4px 0' }} />
        <Row label="Lifetime spent" value={`${spent_ru_lifetime.toLocaleString()} RU`} dimmed />
      </div>
    </div>
  )
}

function Row({
  label,
  value,
  dimmed,
  accent,
}: {
  label: string
  value: string
  dimmed?: boolean
  accent?: boolean
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
      <span style={{ color: 'var(--muted)' }}>{label}</span>
      <span
        style={{
          color: accent ? '#34d399' : dimmed ? 'var(--subtext)' : 'var(--text)',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {value}
      </span>
    </div>
  )
}
