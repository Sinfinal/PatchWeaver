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

const sectionLabelMap: Record<string, string> = {
  risk_rules: "风险规则",
  patch_author_guide: "补丁作者指南",
  primitive_rules: "原语规则",
  smpl_templates: "SmPL 模板",
  livepatch: "Livepatch 规则",
};

function formatSummaryLabel(key: string): string {
  return sectionLabelMap[key] ?? key.replace(/_/g, " ");
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
      <SectionCard title="规则体系" subtitle="管理风险规则、原语规则和 Recipe，对改写过程提供约束。">
        <div className="pw-highlight-grid">
          {ruleHighlights.map((item) => (
            <div key={item.title} className="pw-mini-card">
              <strong>{item.title}</strong>
              <div className="pw-inline-note">{item.description}</div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="目录约定" subtitle="列出规则与配方在仓库中的固定路径，便于联调和排查。">
        <div className="pw-kv">
          {directoryFacts.map((item) => (
            <div key={item.label} className="pw-kv-item">
              <span className="pw-kv-label">{item.label}</span>
              <div className="pw-kv-value">{item.value}</div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="实时目录扫描" subtitle="展示当前后端扫描到的规则目录和文件索引。">
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
              <SectionCard key={name} title={sectionLabelMap[name] ?? name} subtitle={section.path}>
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
