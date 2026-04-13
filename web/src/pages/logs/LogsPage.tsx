import { useQuery } from "@tanstack/react-query";
import { CodePanel } from "../../components/code/CodePanel";
import { SectionCard } from "../../components/layout/SectionCard";
import { apiGet } from "../../services/http";

type LogsResponse = {
  system_log: { path: string; exists: boolean; lines: string[] };
  latest_build_log?: { path: string; exists: boolean; lines: string[] } | null;
};

export function LogsPage(): JSX.Element {
  const query = useQuery({
    queryKey: ["logs"],
    queryFn: () => apiGet<LogsResponse>("/logs"),
  });

  if (query.isLoading) {
    return <div className="pw-empty">日志加载中...</div>;
  }

  if (query.isError || !query.data) {
    return <div className="pw-empty">日志加载失败。</div>;
  }

  return (
    <div className="pw-grid two">
      <SectionCard title="系统日志">
        <CodePanel title="system_log" path={query.data.system_log.path} content={query.data.system_log.lines.join("\n")} />
      </SectionCard>
      <SectionCard title="最近构建日志">
        <CodePanel
          title="latest_build_log"
          path={query.data.latest_build_log?.path}
          content={query.data.latest_build_log?.lines.join("\n")}
        />
      </SectionCard>
    </div>
  );
}
