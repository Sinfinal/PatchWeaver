import { useQuery } from "@tanstack/react-query";
import { CodePanel } from "../../components/code/CodePanel";
import { SectionCard } from "../../components/layout/SectionCard";
import { logGuides } from "../../content/projectContent";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { apiGet } from "../../services/http";

type LogsResponse = {
  system_log: { path: string; exists: boolean; lines: string[] };
  latest_build_log?: { path: string; exists: boolean; lines: string[] } | null;
};

export function LogsPage(): JSX.Element {
  const liveQueryOptions = useLiveQueryOptions();
  const query = useQuery({
    queryKey: ["logs"],
    queryFn: () => apiGet<LogsResponse>("/logs"),
    ...liveQueryOptions,
  });

  return (
    <div className="pw-grid">
      <SectionCard title="排障入口" subtitle="日志页只做两件事：先判断是系统层问题，还是构建链路问题。">
        <div className="pw-highlight-grid">
          {logGuides.map((item) => (
            <div key={item.title} className="pw-mini-card">
              <strong>{item.title}</strong>
              <div className="pw-inline-note">{item.description}</div>
            </div>
          ))}
        </div>
      </SectionCard>

      {query.isLoading ? <div className="pw-note-banner">正在拉取日志尾流...</div> : null}
      {query.isError ? <div className="pw-note-banner">当前无法获取日志接口数据，日志面板会在后端可用后自动填充。</div> : null}

      <div className="pw-grid two">
        <SectionCard title="系统日志">
          <CodePanel
            title="system_log"
            path={query.data?.system_log.path}
            content={query.data?.system_log.lines.join("\n")}
            emptyText="暂无系统日志内容。"
          />
        </SectionCard>
        <SectionCard title="最近一次构建日志">
          <CodePanel
            title="latest_build_log"
            path={query.data?.latest_build_log?.path}
            content={query.data?.latest_build_log?.lines.join("\n")}
            emptyText="暂无最近一次构建日志。"
          />
        </SectionCard>
      </div>
    </div>
  );
}
