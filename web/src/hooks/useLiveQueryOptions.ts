import { useUiStore } from "../store/uiStore";

export function useLiveQueryOptions(): { refetchInterval: number | false } {
  const autoRefresh = useUiStore((state) => state.autoRefresh);
  const refreshIntervalSec = useUiStore((state) => state.refreshIntervalSec);

  return {
    refetchInterval: autoRefresh ? refreshIntervalSec * 1000 : false,
  };
}
