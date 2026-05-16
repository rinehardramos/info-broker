/**
 * Wallet page — UI-P4 + Enhancement 3.4
 *
 * Layout:
 *   WalletBalance  |  BurnChart
 *   FloorConfig
 *   TopupSection
 *   TransactionHistory
 */
import IconRail from '@/components/layout/IconRail'
import { WalletBalance } from '@/components/wallet/WalletBalance'
import { BurnChart } from '@/components/wallet/BurnChart'
import { FloorConfig } from '@/components/wallet/FloorConfig'
import { TopupSection } from '@/components/wallet/TopupSection'
import { TransactionHistory } from '@/components/wallet/TransactionHistory'
import { TemplatesSection } from '@/components/wallet/TemplatesSection'
import { useWallet, useWalletForecast } from '@/hooks/useWallet'

export default function Wallet() {
  const { data: wallet, isLoading: walletLoading, isError: walletError } = useWallet()
  const { data: forecast, isLoading: forecastLoading } = useWalletForecast()

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <div className="flex-1 overflow-auto p-6 space-y-5">
        <h1 className="text-lg font-semibold">Wallet</h1>

        {walletError && (
          <div
            style={{
              padding: '12px 16px',
              borderRadius: 8,
              background: 'rgba(248,113,113,0.08)',
              border: '1px solid rgba(248,113,113,0.25)',
              color: '#f87171',
              fontSize: 13,
            }}
          >
            Failed to load wallet. Please refresh.
          </div>
        )}

        {walletLoading && (
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>Loading wallet…</div>
        )}

        {/* Top row: balance + burn chart */}
        {wallet && (
          <>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <WalletBalance wallet={wallet} />

              {forecast ? (
                <BurnChart forecast={forecast} />
              ) : (
                <div
                  style={{
                    flex: 1,
                    minWidth: 220,
                    background: 'var(--panel)',
                    border: '1px solid var(--border)',
                    borderRadius: 12,
                    padding: '20px 24px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 12,
                    color: 'var(--muted)',
                  }}
                >
                  {forecastLoading ? 'Loading forecast…' : 'No forecast data yet'}
                </div>
              )}
            </div>

            {/* Floor config */}
            <FloorConfig wallet={wallet} />
          </>
        )}

        {/* Top-up section (always visible) */}
        <TopupSection />

        {/* Transaction history */}
        <TransactionHistory />

        {/* Saved query templates */}
        <TemplatesSection />
      </div>
      <IconRail />
    </div>
  )
}
