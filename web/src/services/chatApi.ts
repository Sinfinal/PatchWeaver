import { apiPost } from "./http";
import type { ChatResponse, SuggestedAction } from "../types/chat";

export function sendMessage(
  message: string,
  sessionId: string,
  context: Record<string, string>,
): Promise<ChatResponse> {
  return apiPost<ChatResponse>("/chat", {
    message,
    session_id: sessionId,
    context,
  });
}

export async function runSuggestedAction(action: SuggestedAction): Promise<void> {
  if (action.type === "create_task") {
    await apiPost("/tasks", {
      cve_id: action.payload.cve_id,
      target_kernel: action.payload.kernel || undefined,
      auto_run: false,
    });
    return;
  }
  if (action.type === "start_auto_run") {
    await apiPost(`/tasks/${String(action.payload.task_id)}/run`);
    return;
  }
  if (action.type === "run_doctor_repair") {
    await apiPost("/doctor/repair");
    return;
  }
  throw new Error(`暂不支持的建议动作：${action.type}`);
}
