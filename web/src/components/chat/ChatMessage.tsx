import type { ChatMessage as ChatMessageModel, SuggestedAction } from "../../types/chat";

type ChatMessageProps = {
  message: ChatMessageModel;
  onAction: (action: SuggestedAction) => void;
};

export function ChatMessage({ message, onAction }: ChatMessageProps): JSX.Element {
  const response = message.response;
  return (
    <div className={`pw-chat-message ${message.role}`}>
      <div className="pw-chat-message-role">{message.role === "user" ? "你" : "助手"}</div>
      {response?.risk === "high" ? <div className="pw-chat-risk">高风险建议，需要确认后再执行</div> : null}
      <div className="pw-chat-message-content">{message.content}</div>
      {response?.tool_calls.length ? (
        <div className="pw-chat-tool-row">
          {response.tool_calls.map((tool, index) => (
            <span className={`pw-chat-tool ${tool.status}`} key={`${tool.name}-${index}`}>
              {formatToolName(tool.name)} · {formatToolStatus(tool.status)}
            </span>
          ))}
        </div>
      ) : null}
      {response?.evidence_refs.length ? (
        <details className="pw-chat-evidence">
          <summary>证据引用 {response.evidence_refs.length}</summary>
          <ul>
            {response.evidence_refs.map((ref) => (
              <li key={ref}>{ref}</li>
            ))}
          </ul>
        </details>
      ) : null}
      {response?.suggested_actions.length ? (
        <div className="pw-chat-action-row">
          {response.suggested_actions.map((action) => (
            <button className="pw-btn" key={`${action.type}-${action.label}`} onClick={() => onAction(action)} type="button">
              {action.requires_confirmation ? "确认后" : "执行"} · {action.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function formatToolName(name: string): string {
  const labels: Record<string, string> = {
    get_overview: "系统总览",
    get_task_detail: "任务详情",
    explain_failure: "失败解释",
    get_doctor_report: "环境诊断",
    get_task_report: "任务报告",
    get_artifact_content: "产物内容",
    search_docs_rag: "文档检索",
  };
  return labels[name] ?? name;
}

function formatToolStatus(status: string): string {
  const labels: Record<string, string> = {
    success: "成功",
    error: "错误",
    skipped: "跳过",
  };
  return labels[status] ?? status;
}
