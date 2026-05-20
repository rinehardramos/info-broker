import { QueryClient } from '@tanstack/react-query'

type HttpError = Error & { status?: number }

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          const status = (error as HttpError)?.status
          if (status && status >= 400 && status < 500) return false
          return failureCount < 2
        },
      },
      mutations: {
        retry: 0,
      },
    },
  })
}
