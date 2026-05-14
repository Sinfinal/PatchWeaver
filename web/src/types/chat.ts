export interface ToolCallTrace {
  name: string;
  status: "success" | "error" | "skipped";
  summary: string;
}

export interface SuggestedAction {
  type: string;
  label: string;
  payload: Record<string, unknown>;
  requires_confirmation: boolean;
}

export interface ChatResponse {
  answer: string;
  evidence_refs: string[];
  tool_calls: ToolCallTrace[];
  suggested_actions: SuggestedAction[];
  risk: "low" | "medium" | "high";
  requires_confirmation: boolean;
  session_id: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
  timestamp: number;
}
