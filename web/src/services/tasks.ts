import { apiGet, apiPost } from "./http";
import type {
  ArtifactContentResponse,
  ArtifactTreeResponse,
  CreateTaskPayload,
  TaskActionResponse,
  TaskDetailResponse,
  TaskListResponse,
} from "../types/tasks";

export function fetchTasks(params?: Record<string, string | number | undefined>): Promise<TaskListResponse> {
  return apiGet<TaskListResponse>("/tasks", params);
}

export function createTask(payload: CreateTaskPayload): Promise<{
  status?: string;
  created?: boolean;
  auto_run?: boolean;
  auto_run_status?: string;
  message?: string;
  task: TaskDetailResponse["task"];
  existing_task?: TaskDetailResponse["task"];
}> {
  return apiPost<{
    status?: string;
    created?: boolean;
    auto_run?: boolean;
    auto_run_status?: string;
    message?: string;
    task: TaskDetailResponse["task"];
    existing_task?: TaskDetailResponse["task"];
  }>("/tasks", payload);
}

export function fetchTaskDetail(taskId: string): Promise<TaskDetailResponse> {
  return apiGet<TaskDetailResponse>(`/tasks/${taskId}`);
}

export function analyzeTask(taskId: string): Promise<TaskActionResponse> {
  return apiPost<TaskActionResponse>(`/tasks/${taskId}/analyze`);
}

export function runTask(taskId: string): Promise<TaskActionResponse> {
  return apiPost<TaskActionResponse>(`/tasks/${taskId}/run`);
}

export function reportTask(taskId: string): Promise<TaskActionResponse> {
  return apiPost<TaskActionResponse>(`/tasks/${taskId}/report`);
}

export function fetchReplay(taskId: string): Promise<TaskDetailResponse["replay"]> {
  return apiGet<TaskDetailResponse["replay"]>(`/tasks/${taskId}/replay`);
}

export function fetchArtifacts(taskId: string): Promise<ArtifactTreeResponse> {
  return apiGet<ArtifactTreeResponse>(`/tasks/${taskId}/artifacts`);
}

export function fetchArtifactContent(taskId: string, path: string): Promise<ArtifactContentResponse> {
  return apiGet<ArtifactContentResponse>(`/tasks/${taskId}/artifacts/content`, { path });
}
