import { apiGet } from "./http";
import type { OverviewResponse } from "../types/overview";

export function fetchOverview(): Promise<OverviewResponse> {
  return apiGet<OverviewResponse>("/overview");
}

export function fetchEvents(limit = 20): Promise<{ items: OverviewResponse["events"] }> {
  return apiGet<{ items: OverviewResponse["events"] }>("/events", { limit });
}
