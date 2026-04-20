import { useQuery } from "@tanstack/react-query";
import { MetricCard } from "../../components/cards/MetricCard";
import { SectionCard } from "../../components/layout/SectionCard";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { apiGet } from "../../services/http";
import { ruleHighlights } from "../../content/projectContent";

type RulesResponse = {
  sections: Record<string, { path: string; exists: boolean; files: Array<{ name: string; relative_path: string; size: number }> }>;
  summary: Record<string, number>;
};

const directoryFacts = [
  { label: "风险规则目录", value: "rules/risk_rules" },
  { label: "补丁作者指南", value: "rules/risk_rules/patch_author_guide" },
  { label: "原语规则目录", value: "rules/primitive_rules" },
  { label: "livepatch 规则目录", value: "rules/primitive_rules/livepatch" },
  { label: "默认 Recipe 清单", value: "recipes/manifests/default.yaml" },
];

function formatSummaryLabel(key: string): string {
  return key.replace(/_/g, " ");
}

export function RulesPage(): JSX.Element {
  const liveQueryOptions = useLiveQueryOptions();
  const query = useQuery({
    queryKey: ["rules"],
    queryFn: () => apiGet<RulesResponse>("/rules"),
    ...liveQueryOptions,
  });

  return (
    <div className="pw-grid">
      <SectionCard title="规则体系" subtitle="围绕 kpatch/livepatch 约束，对 patch 做风险识别、改写约束和 Recipe 路由。">
        <div className="pw-highlight-grid">
          {ruleHighlights.map((item) => (
            <div key={item.title} className="pw-mini-card">
              <strong>{item.title}</strong>
              <div className="pw-inline-note">{item.description}</div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="目录约定" subtitle="这些路径来自当前仓库配置，用于说明规则和配方在工程里的摆放位置。">
        <div className="pw-kv">
          {directoryFacts.map((item) => (
            <div key={item.label} className="pw-kv-item">
              <span className="pw-kv-label">{item.label}</span>
              <div className="pw-kv-value">{item.value}</div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="实时目录扫描" subtitle="来自 `/rules` 接口，用于确认后端当前能看到哪些规则文件。">
        {query.isLoading ? <div className="pw-note-banner">正在加载规则目录索引...</div> : null}
        {query.isError ? <div className="pw-note-banner">当前无法获取实时规则索引，先保留静态目录说明。</div> : null}
        {query.data ? (
          <div className="pw-grid">
            <div className="pw-grid metrics">
              {Object.entries(query.data.summary).map(([key, value]) => (
                <MetricCard key={key} label={formatSummaryLabel(key)} value={value} />
              ))}
            </div>
            {Object.entries(query.data.sections).map(([name, section]) => (
              <SectionCard key={name} title={name} subtitle={section.path}>
                {section.files.length > 0 ? (
                  <div className="pw-list">
                    {section.files.map((file) => (
                      <div key={file.relative_path} className="pw-list-item">
                        <strong>{file.name}</strong>
                        <div className="pw-inline-note">{file.relative_path}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="pw-empty">当前目录下还没有可展示的规则文件。</div>
                )}
              </SectionCard>
            ))}
          </div>
        ) : null}
      </SectionCard>
    </div>
  );
}
