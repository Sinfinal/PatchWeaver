import { useQuery } from "@tanstack/react-query";
import { CodePanel } from "../../components/code/CodePanel";
import { SectionCard } from "../../components/layout/SectionCard";
import { apiGet } from "../../services/http";

export function SettingsPage(): JSX.Element {
  const query = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiGet<Record<string, unknown>>("/settings"),
  });

  if (query.isLoading) {
    return <div className="pw-empty">设置加载中...</div>;
  }

  if (query.isError || !query.data) {
    return <div className="pw-empty">设置加载失败。</div>;
  }

  return (
    <SectionCard title="当前配置" subtitle="系统、构建、验证、Prompt、Skill 和规则配置快照">
      <CodePanel title="settings.json" content={JSON.stringify(query.data, null, 2)} />
    </SectionCard>
  );
}
