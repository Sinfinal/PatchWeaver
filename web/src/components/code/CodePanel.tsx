import type { ReactNode } from "react";

type CodePanelProps = {
  title: string;
  path?: string;
  content?: string;
  emptyText?: string;
  actions?: ReactNode;
};

export function CodePanel({ title, path, content, emptyText, actions }: CodePanelProps): JSX.Element {
  return (
    <div className="pw-code-panel">
      <div className="pw-code-toolbar">
        <div>
          <strong>{title}</strong>
          <div className="pw-inline-note">{path ?? "未选择文件"}</div>
        </div>
        {actions}
      </div>
      <pre className="pw-code-content">{content && content.length > 0 ? content : emptyText ?? "暂无内容"}</pre>
    </div>
  );
}
