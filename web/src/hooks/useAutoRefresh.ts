import { useEffect } from "react";

export function useAutoRefresh(callback: () => void, enabled: boolean, intervalSec: number): void {
  useEffect(() => {
    if (!enabled || intervalSec <= 0) {
      return undefined;
    }
    const timer = window.setInterval(() => callback(), intervalSec * 1000);
    return () => window.clearInterval(timer);
  }, [callback, enabled, intervalSec]);
}
