import { apiGet } from "./http";
import type {
  EvaluationFixtureDetailResponse,
  EvaluationGroupListResponse,
  EvaluationGroupSummaryResponse,
  TaskReportResponse,
} from "../types/reports";

export function fetchTaskReport(taskId: string): Promise<TaskReportResponse> {
  return apiGet<TaskReportResponse>(`/reports/tasks/${taskId}`);
}

export function fetchEvaluationGroups(): Promise<EvaluationGroupListResponse> {
  return apiGet<EvaluationGroupListResponse>("/evaluations/groups");
}

export function fetchEvaluationGroupSummary(groupId: string): Promise<EvaluationGroupSummaryResponse> {
  return apiGet<EvaluationGroupSummaryResponse>(`/evaluations/${groupId}/summary`);
}

export function fetchEvaluationFixtureDetail(groupId: string, fixtureId: string): Promise<EvaluationFixtureDetailResponse> {
  return apiGet<EvaluationFixtureDetailResponse>(`/evaluations/${groupId}/fixtures/${fixtureId}`);
}
