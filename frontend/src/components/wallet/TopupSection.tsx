/**
 * TopupSection — top-up amount selector + Stripe placeholder.
 *
 * TODO (post-MVP, arch P8): wire real Stripe checkout session via
 *   POST /v3/wallet/topup → returns Stripe checkout URL → redirect.
 * TODO (post-MVP): auto-topup config (toggle, trigger threshold, amount, monthly cap, payment method).
 */
import { useState } from 'react'

const PRESET_AMOUNTS = [10, 50, 100, 250]
const RU_PER_DOLLAR = 10

export function TopupSection() {
  const [selected, setSelected] = useState<number | null>(null)
  const [custom, setCustom] = useState('')

  const effectiveAmount = selected ?? (custom ? Number(custom) : null)
  const estimatedRu = effectiveAmount ? effectiveAmount * RU_PER_DOLLAR : null

  return (
    <div
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        padding: '20px 24px',
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Buy more RU</div>
      <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 14 }}>
        $1 = {RU_PER_DOLLAR} RU
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        {PRESET_AMOUNTS.map(amt => (
          <button
            key={amt}
            onClick={() => { setSelected(amt === selected ? null : amt); setCustom('') }}
            style={{
              padding: '6px 14px',
              borderRadius: 6,
              border: `1px solid ${selected === amt ? 'rgba(167,139,250,0.6)' : 'var(--border)'}`,
              background: selected === amt ? 'rgba(167,139,250,0.14)' : 'transparent',
              color: selected === amt ? '#a78bfa' : 'var(--subtext)',
              fontSize: 13,
              cursor: 'pointer',
              fontVariantNumeric: 'tabular-nums',
              transition: 'background 0.1s, color 0.1s, border-color 0.1s',
            }}
          >
            ${amt}
          </button>
        ))}

        <input
          type="number"
          min={1}
          placeholder="Custom $"
          value={custom}
          onChange={e => { setCustom(e.target.value); setSelected(null) }}
          style={{
            width: 88,
            padding: '6px 10px',
            borderRadius: 6,
            border: `1px solid ${custom ? 'rgba(167,139,250,0.6)' : 'var(--border)'}`,
            background: 'var(--bg)',
            color: 'var(--text)',
            fontSize: 13,
          }}
        />
      </div>

      {estimatedRu !== null && (
        <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12 }}>
          You will receive{' '}
          <strong style={{ color: '#34d399' }}>{estimatedRu.toLocaleString()} RU</strong>
        </div>
      )}

      <button
        disabled
        title="Stripe checkout coming soon"
        style={{
          padding: '8px 20px',
          borderRadius: 8,
          border: '1px solid var(--border)',
          background: 'var(--bg)',
          color: 'var(--muted)',
          fontSize: 13,
          cursor: 'not-allowed',
          opacity: 0.6,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <span>⚠</span>
        Stripe checkout coming soon
      </button>
    </div>
  )
}
