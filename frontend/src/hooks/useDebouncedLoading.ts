import { useEffect, useState } from 'react'

/**
 * Suppress loading indicators that would flash for less than `delayMs`.
 * Prevents the <250 ms spinner-blink anti-pattern on cache hits or fast networks.
 *
 * Returns true only when `isLoading` has been continuously true for `delayMs`.
 */
export function useDebouncedLoading(isLoading: boolean, delayMs = 250): boolean {
  const [show, setShow] = useState(false)

  useEffect(() => {
    if (!isLoading) {
      setShow(false)
      return
    }
    const t = setTimeout(() => setShow(true), delayMs)
    return () => clearTimeout(t)
  }, [isLoading, delayMs])

  return show
}
