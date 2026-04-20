import { useMemo } from "react";
import { useUiStore } from "../store/uiStore";

export function useLiveQueryOptions() {
  const autoRefresh = useUiStore((state) => state.autoRefresh);
  const refreshIntervalSec = useUiStore((state) => state.refreshIntervalSec);
  const refetchInterval: number | false = autoRefresh ? refreshIntervalSec * 1000 : false;

  return useMemo(
    () => ({
      staleTime: 0,
      refetchOnWindowFocus: false as const,
      refetchInterval,
    }),
    [refetchInterval],
  );
}
