import { useQuery } from "@tanstack/react-query";
import { CodePanel } from "../../components/code/CodePanel";
import { SectionCard } from "../../components/layout/SectionCard";
import { buildProfiles, settingsFacts } from "../../content/projectContent";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { apiGet } from "../../services/http";

export function SettingsPage(): JSX.Element {
  const liveQueryOptions = useLiveQueryOptions();
  const query = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiGet<Record<string, unknown>>("/settings"),
    ...liveQueryOptions,
  });

  return (
    <div className="pw-grid">
      <SectionCard title="系统默认值">
        <div className="pw-highlight-grid">
          {settingsFacts.map((item) => (
            <div key={item.title} className="pw-mini-card">
              <strong>{item.title}</strong>
              <div className="pw-inline-note">{item.description}</div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="运行档位">
        <div className="pw-highlight-grid">
          {buildProfiles.map((profile) => (
            <div key={profile.name} className="pw-mini-card">
              <strong>
                {profile.name} · {profile.attempts}
              </strong>
              <div className="pw-inline-note">{profile.description}</div>
              <div className="pw-step-artifacts">
                {profile.highlights.map((highlight) => (
                  <span key={highlight} className="pw-step-artifact">
                    {highlight}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="实时配置快照">
        {query.isLoading ? <div className="pw-note-banner">正在加载配置快照...</div> : null}
        {query.isError ? <div className="pw-note-banner">当前无法获取实时配置，只展示静态默认值与 profile 说明。</div> : null}
        <CodePanel title="settings.json" content={query.data ? JSON.stringify(query.data, null, 2) : undefined} emptyText="暂无配置快照。" />
      </SectionCard>
    </div>
  );
}
