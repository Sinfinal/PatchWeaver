import { useQuery } from "@tanstack/react-query";
import { SectionCard } from "../../components/layout/SectionCard";
import { StatusBadge } from "../../components/status/StatusBadge";
import { apiGet } from "../../services/http";

type SkillsResponse = {
  source_priority: string[];
  enabled_skills: string[];
  entries: Array<{
    skill_name: string;
    stage_name: string;
    source_layer: string;
    visibility: string;
    enabled: boolean;
    entry_kind: string;
    description: string;
    manifest_path: string;
  }>;
};

export function SkillsPage(): JSX.Element {
  const query = useQuery({
    queryKey: ["skills"],
    queryFn: () => apiGet<SkillsResponse>("/skills"),
  });

  if (query.isLoading) {
    return <div className="pw-empty">Skill 清单加载中...</div>;
  }

  if (query.isError || !query.data) {
    return <div className="pw-empty">Skill 清单加载失败。</div>;
  }

  return (
    <div className="pw-grid">
      <SectionCard title="来源优先级" subtitle="当前配置声明的 Skill 解析顺序">
        <div className="pw-btn-row">
          {query.data.source_priority.map((item) => (
            <span key={item} className="pw-chip">
              {item}
            </span>
          ))}
        </div>
      </SectionCard>
      <SectionCard title="Skill 清单" subtitle="按 stage 和 source_layer 汇总">
        <table className="pw-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Stage</th>
              <th>Source</th>
              <th>Status</th>
              <th>Manifest</th>
            </tr>
          </thead>
          <tbody>
            {query.data.entries.map((item) => (
              <tr key={`${item.source_layer}-${item.skill_name}-${item.stage_name}`}>
                <td>{item.skill_name}</td>
                <td>{item.stage_name}</td>
                <td>{item.source_layer}</td>
                <td>
                  <StatusBadge value={item.enabled ? "enabled" : "disabled"} />
                </td>
                <td>{item.manifest_path}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>
    </div>
  );
}
