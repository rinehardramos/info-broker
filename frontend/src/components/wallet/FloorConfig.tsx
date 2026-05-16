/**
 * FloorConfig — slider + input to set floor_ru.
 * Shows spendable = available - floor in real time.
 */
import { useState } from 'react'
import type { WalletSnapshot } from '@/api/v3'
import { useUpdateFloor } from '@/hooks/useWallet'

interface Props {
  wallet: WalletSnapshot
}

export function FloorConfig({ wallet }: Props) {
  const [draftFloor, setDraftFloor] = useState(wallet.floor_ru)
  const [saved, setSaved] = useState(false)
  const updateFloor = useUpdateFloor()

  const spendable = Math.max(0, wallet.available_ru - draftFloor)
  const maxFloor = Math.max(0, wallet.available_ru - 1)

  function handleSave() {
    updateFloor.mutate(draftFloor, {
      onSuccess: () => {
        setSaved(true)
        setTimeout(() => setSaved(false), 2000)
      },
    })
  }

  return (
    <div
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        padding: '20px 24px',
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Floor RU</div>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12 }}>
        Never let my balance drop below this amount
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <input
          type="range"
          min={0}
          max={maxFloor}
          value={draftFloor}
          onChange={e => setDraftFloor(Number(e.target.value))}
          style={{ flex: 1, accentColor: '#a78bfa' }}
        />
        <input
          type="number"
          min={0}
          max={maxFloor}
          value={draftFloor}
          onChange={e => setDraftFloor(Math.max(0, Math.min(maxFloor, Number(e.target.value))))}
          style={{
            width: 72,
            padding: '4px 8px',
            borderRadius: 6,
            border: '1px solid var(--border)',
            background: 'var(--bg)',
            color: 'var(--text)',
            fontSize: 13,
            fontVariantNumeric: 'tabular-nums',
          }}
        />
        <span style={{ color: 'var(--muted)', fontSize: 12 }}>RU</span>
      </div>

      <div
        style={{
          marginTop: 10,
          fontSize: 12,
          color: 'var(--muted)',
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <span>
          Spendable:{' '}
          <strong style={{ color: '#34d399' }}>{spendable.toLocaleString()} RU</strong>
        </span>
        <span style={{ color: 'var(--subtext)' }}>
          {wallet.available_ru.toLocaleString()} – {draftFloor.toLocaleString()} = {spendable.toLocaleString()}
        </span>
      </div>

      <button
        onClick={handleSave}
        disabled={updateFloor.isPending || draftFloor === wallet.floor_ru}
        style={{
          marginTop: 12,
          padding: '6px 16px',
          borderRadius: 6,
          border: '1px solid rgba(167,139,250,0.4)',
          background: 'rgba(167,139,250,0.12)',
          color: '#a78bfa',
          fontSize: 12,
          cursor: draftFloor === wallet.floor_ru ? 'default' : 'pointer',
          opacity: draftFloor === wallet.floor_ru ? 0.5 : 1,
          transition: 'opacity 0.12s',
        }}
      >
        {updateFloor.isPending ? 'Saving…' : saved ? 'Saved' : 'Save floor'}
      </button>

      {updateFloor.isError && (
        <div style={{ marginTop: 6, fontSize: 12, color: '#f87171' }}>
          Failed to update floor — try again
        </div>
      )}
    </div>
  )
}
