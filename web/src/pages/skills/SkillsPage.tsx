import { useQuery } from "@tanstack/react-query";
import { MetricCard } from "../../components/cards/MetricCard";
import { SectionCard } from "../../components/layout/SectionCard";
import { StatusBadge } from "../../components/status/StatusBadge";
import { skillHighlights } from "../../content/projectContent";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
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

const dispatchFacts = [
  { title: "默认 profile", description: "contest" },
  { title: "调度策略", description: "skill_first，必要时 fallback 到 direct_worker" },
  { title: "允许并行只读子任务", description: "最多 2 个，只限 retrieval / failure_analysis / reporting" },
  { title: "写操作边界", description: "write actions via harness only" },
];

export function SkillsPage(): JSX.Element {
  const liveQueryOptions = useLiveQueryOptions();
  const query = useQuery({
    queryKey: ["skills"],
    queryFn: () => apiGet<SkillsResponse>("/skills"),
    ...liveQueryOptions,
  });

  return (
    <div className="pw-grid">
      <SectionCard title="技能调度设计" subtitle="定义阶段到技能的路由关系，统一主链路的执行入口。">
        <div className="pw-highlight-grid">
          {dispatchFacts.map((item) => (
            <div key={item.title} className="pw-mini-card">
              <strong>{item.title}</strong>
              <div className="pw-inline-note">{item.description}</div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="核心技能" subtitle="列出当前启用的阶段技能及其在主链路中的职责。">
        <div className="pw-highlight-grid">
          {skillHighlights.map((item) => (
            <div key={item.title} className="pw-mini-card">
              <strong>{item.title}</strong>
              <div className="pw-inline-note">{item.description}</div>
              {item.meta ? (
                <div className="pw-inline-note" style={{ marginTop: 6 }}>
                  {item.meta}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="实时 Skill Registry" subtitle="读取后端注册表，用于核对技能加载状态和来源层级。">
        {query.isLoading ? <div className="pw-note-banner">正在加载技能注册表...</div> : null}
        {query.isError ? <div className="pw-note-banner">当前无法获取实时 Skill Registry，先保留静态调度说明。</div> : null}
        {query.data ? (
          <div className="pw-grid">
            <div className="pw-grid metrics">
              <MetricCard label="技能条目" value={query.data.entries.length} />
              <MetricCard label="已启用技能" value={query.data.enabled_skills.length} />
              <MetricCard label="来源优先级" value={query.data.source_priority.join(" > ")} />
            </div>
            <div className="pw-btn-row">
              {query.data.enabled_skills.map((item) => (
                <span key={item} className="pw-chip">
                  {item}
                </span>
              ))}
            </div>
            <div className="pw-table-shell">
              <table className="pw-table">
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>阶段</th>
                    <th>来源</th>
                    <th>状态</th>
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
            </div>
          </div>
        ) : null}
      </SectionCard>
    </div>
  );
}
