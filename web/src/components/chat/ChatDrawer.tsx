import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { runSuggestedAction, sendMessage } from "../../services/chatApi";
import type { ChatMessage as ChatMessageModel, SuggestedAction } from "../../types/chat";
import { ChatMessage } from "./ChatMessage";

type ChatDrawerProps = {
  open: boolean;
  onClose: () => void;
};

export function ChatDrawer({ open, onClose }: ChatDrawerProps): JSX.Element | null {
  const location = useLocation();
  const [sessionId, setSessionId] = useState("");
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessageModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const pageContext = useMemo(() => buildPageContext(location.pathname), [location.pathname]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  if (!open) {
    return null;
  }

  async function submitMessage(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || loading) {
      return;
    }
    setDraft("");
    setError(null);
    setLoading(true);
    setMessages((current) => [...current, { role: "user", content: text, timestamp: Date.now() }]);
    try {
      const response = await sendMessage(text, sessionId, pageContext);
      setSessionId(response.session_id);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: response.answer,
          response,
          timestamp: Date.now(),
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "消息发送失败");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitMessage();
    }
  }

  async function handleAction(action: SuggestedAction) {
    if (action.requires_confirmation && !window.confirm(`确认执行：${action.label}`)) {
      return;
    }
    try {
      await runSuggestedAction(action);
      setMessages((current) => [
        ...current,
        { role: "assistant", content: `动作已提交：${action.label}`, timestamp: Date.now() },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "动作执行失败");
    }
  }

  return (
    <div className="pw-chat-overlay" role="dialog" aria-label="Chat Assistant">
      <aside className="pw-chat-drawer">
        <header className="pw-chat-header">
          <div>
            <strong>Chat Assistant</strong>
            <span>只读查询 · 证据引用 · 操作需确认</span>
          </div>
          <button className="pw-chat-close" type="button" onClick={onClose} aria-label="关闭聊天面板">
            ×
          </button>
        </header>
        <div className="pw-chat-list" ref={listRef}>
          {messages.length === 0 ? (
            <div className="pw-chat-empty">
              可以问我系统状态、环境诊断、任务失败原因或报告位置
            </div>
          ) : (
            messages.map((item) => <ChatMessage key={`${item.timestamp}-${item.role}`} message={item} onAction={handleAction} />)
          )}
          {loading ? <div className="pw-chat-loading">正在查询证据</div> : null}
        </div>
        {error ? <div className="pw-chat-error">{error}</div> : null}
        <form className="pw-chat-input-row" onSubmit={(event) => void submitMessage(event)}>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入问题，Enter 发送，Shift+Enter 换行"
            disabled={loading}
          />
          <button className="pw-btn primary" type="submit" disabled={loading || !draft.trim()}>
            发送
          </button>
        </form>
      </aside>
    </div>
  );
}

function buildPageContext(pathname: string): Record<string, string> {
  const taskMatch = pathname.match(/\/tasks\/([^/]+)/);
  return {
    page: pathname,
    task_id: taskMatch?.[1] ?? "",
  };
}
