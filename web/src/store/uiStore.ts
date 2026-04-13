import { create } from "zustand";

type UiState = {
  autoRefresh: boolean;
  refreshIntervalSec: number;
  selectedAttemptNo: number | null;
  setAutoRefresh: (value: boolean) => void;
  setRefreshIntervalSec: (value: number) => void;
  setSelectedAttemptNo: (value: number | null) => void;
};

export const useUiStore = create<UiState>((set) => ({
  autoRefresh: true,
  refreshIntervalSec: 20,
  selectedAttemptNo: null,
  setAutoRefresh: (value) => set({ autoRefresh: value }),
  setRefreshIntervalSec: (value) => set({ refreshIntervalSec: value }),
  setSelectedAttemptNo: (value) => set({ selectedAttemptNo: value }),
}));
