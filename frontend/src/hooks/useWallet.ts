/**
 * useWallet — encapsulates all wallet API calls for UI-P4.
 * Provides reactive queries and mutation helpers so Wallet.tsx and
 * sub-components don't import from the API layer directly.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getWallet,
  getWalletTransactions,
  getWalletForecast,
  putWalletFloor,
  getRunCostBreakdown,
  type WalletSnapshot,
  type WalletTransactionsOut,
  type WalletForecast,
  type RunCostBreakdown,
} from '@/api/v3'

export const WALLET_QK = ['wallet'] as const
export const WALLET_TXN_QK = (limit: number, offset: number) =>
  ['wallet', 'transactions', limit, offset] as const
export const WALLET_FORECAST_QK = ['wallet', 'forecast'] as const
export const RUN_COST_QK = (runId: string) => ['run-cost', runId] as const

export function useWallet() {
  return useQuery<WalletSnapshot>({
    queryKey: WALLET_QK,
    queryFn: getWallet,
    staleTime: 15_000,
    refetchInterval: 30_000,
  })
}

export function useWalletTransactions(limit = 50, offset = 0) {
  return useQuery<WalletTransactionsOut>({
    queryKey: WALLET_TXN_QK(limit, offset),
    queryFn: () => getWalletTransactions(limit, offset),
    staleTime: 30_000,
  })
}

export function useWalletForecast() {
  return useQuery<WalletForecast>({
    queryKey: WALLET_FORECAST_QK,
    queryFn: getWalletForecast,
    staleTime: 60_000,
  })
}

export function useUpdateFloor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (floor_ru: number) => putWalletFloor(floor_ru),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: WALLET_QK })
    },
  })
}

export function useRunCostBreakdown(runId: string | null) {
  return useQuery<RunCostBreakdown>({
    queryKey: RUN_COST_QK(runId ?? ''),
    queryFn: () => getRunCostBreakdown(runId!),
    enabled: !!runId,
    staleTime: 60_000,
  })
}
