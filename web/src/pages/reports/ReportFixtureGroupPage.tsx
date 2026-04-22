import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { CodePanel } from "../../components/code/CodePanel";
import { MetricCard } from "../../components/cards/MetricCard";
import { SectionCard } from "../../components/layout/SectionCard";
import { StatusBadge } from "../../components/status/StatusBadge";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { fetchEvaluationGroupSummary } from "../../services/reports";
import { formatPercent, shortenPath } from "../../utils/format";

export function ReportFixtureGroupPage(): JSX.Element {
  const params = useParams<{ fixtureGroup: string }>();
  const fixtureGroup = params.fixtureGroup ?? "";
  const liveQueryOptions = useLiveQueryOptions();
  const query = useQuery({
    queryKey: ["fixture-group", fixtureGroup],
    queryFn: () => fetchEvaluationGroupSummary(fixtureGroup),
    enabled: fixtureGroup.length > 0,
    ...liveQueryOptions,
  });

  const failureRows = useMemo(() => {
    if (!query.data) {
      return [];
    }
    return Object.entries(query.data.summary.failure_distribution ?? {}).sort((left, right) => right[1] - left[1]);
  }, [query.data]);

  if (query.isLoading) {
    return <div className="pw-empty">正在加载分组摘要...</div>;
  }

  if (query.isError || !query.data) {
    return <div className="pw-empty">当前无法读取固定样例分组摘要，请确认 summary.json 已生成。</div>;
  }

  const payload = query.data;

  return (
    <div className="pw-grid">
      <SectionCard
        title={payload.display_name}
        subtitle="当前分组的统计摘要、样例列表和 summary 文件都集中在这个页面。"
        actions={
          <div className="pw-btn-row">
            <Link className="pw-btn" to="/reports">
              返回报告中心
            </Link>
          </div>
        }
      >
        <div className="pw-grid metrics">
          <MetricCard label="样例总数" value={payload.summary.total_fixtures} />
          <MetricCard label="已匹配样例" value={payload.summary.matched_fixtures} />
          <MetricCard label="缺失样例" value={payload.summary.missing_fixtures} />
          <MetricCard label="成功数" value={payload.summary.success_count} />
          <MetricCard label="成功率" value={formatPercent(payload.summary.success_rate)} />
          <MetricCard label="平均尝试轮次" value={payload.summary.average_attempts.toFixed(2)} />
        </div>
      </SectionCard>

      <div className="pw-grid two">
        <SectionCard title="summary.md" subtitle={shortenPath(payload.summary_md_path)}>
          <CodePanel
            title="summary.md"
            path={payload.summary_md_path}
            content={payload.summary_markdown ?? undefined}
            emptyText="当前没有 summary.md 内容。"
          />
        </SectionCard>
        <SectionCard title="summary.json" subtitle={shortenPath(payload.summary_json_path)}>
          <CodePanel
            title="summary.json"
            path={payload.summary_json_path}
            content={JSON.stringify(payload.summary, null, 2)}
            emptyText="当前没有 summary.json 内容。"
          />
        </SectionCard>
      </div>

      <div className="pw-grid two">
        <SectionCard title="失败分布" subtitle="按 summary.json 中的 failure_distribution 展示。">
          {failureRows.length > 0 ? (
            <div className="pw-list">
              {failureRows.map(([name, total]) => (
                <div key={name} className="pw-list-item">
                  <strong>{name}</strong>
                  <div className="pw-inline-note">{total} 次</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="pw-empty">当前没有 failure_distribution 统计。</div>
          )}
        </SectionCard>

        <SectionCard title="单样例列表" subtitle="从这里进入单样例详情，或直接跳到任务级报告页。">
          {payload.fixtures.length > 0 ? (
            <div className="pw-list">
              {payload.fixtures.map((item) => (
                <div key={item.fixture_id} className="pw-list-item">
                  <strong>{item.fixture_id}</strong>
                  <div className="pw-report-inline">
                    <StatusBadge value={item.final_status ?? (item.matched ? "matched" : "missing")} />
                    <span className="pw-inline-note">任务：{item.task_id ?? "未匹配"}</span>
                  </div>
                    <div className="pw-inline-note">{item.cve_id ?? "未记录 CVE"}</div>
                    <div className="pw-inline-note">{item.target_kernel ?? "未记录目标内核"}</div>
                    <div className="pw-report-inline">
                      <Link className="pw-btn" to={`/reports/fixtures/${payload.fixture_group}/${item.fixture_id}`}>
                        查看样例详情
                      </Link>
                    {item.task_id ? (
                      <Link className="pw-btn" to={`/reports/tasks/${item.task_id}`}>
                        任务报告
                      </Link>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="pw-empty">当前分组还没有可展示的样例列表。</div>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
