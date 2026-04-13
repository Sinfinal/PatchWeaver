import { useQuery } from "@tanstack/react-query";
import { SectionCard } from "../../components/layout/SectionCard";
import { apiGet } from "../../services/http";

type RulesResponse = {
  sections: Record<string, { path: string; exists: boolean; files: Array<{ name: string; relative_path: string; size: number }> }>;
  summary: Record<string, number>;
};

export function RulesPage(): JSX.Element {
  const query = useQuery({
    queryKey: ["rules"],
    queryFn: () => apiGet<RulesResponse>("/rules"),
  });

  if (query.isLoading) {
    return <div className="pw-empty">规则目录加载中...</div>;
  }

  if (query.isError || !query.data) {
    return <div className="pw-empty">规则目录加载失败。</div>;
  }

  return (
    <div className="pw-grid">
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
            <div className="pw-empty">当前目录下还没有文件。</div>
          )}
        </SectionCard>
      ))}
    </div>
  );
}
