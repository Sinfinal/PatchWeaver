export function useLiveQueryOptions() {
  return {
    staleTime: 0,
    refetchOnWindowFocus: true as const,
    refetchInterval: false as const,
  };
}
