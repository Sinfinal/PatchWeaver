import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { SectionCard } from "../../components/layout/SectionCard";
import { TaskTable } from "../../components/tables/TaskTable";
import { controlPlanes, projectSummary } from "../../content/projectContent";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { fetchOverview } from "../../services/overview";
import type { TaskListItem } from "../../types/tasks";
import { formatTime, shortenPath, toFixtureGroupPath } from "../../utils/format";

export function OverviewPage(): JSX.Element {
  const liveQueryOptions = useLiveQueryOptions();
  const overviewQuery = useQuery({
    queryKey: ["overview"],
    queryFn: fetchOverview,
    ...liveQueryOptions,
  });

  const overview = overviewQuery.data;
  const runtimeStats = overview
    ? [
        { label: "任务总数", value: overview.metrics.total_tasks, meta: "全部任务" },
        { label: "运行中", value: overview.metrics.running_tasks, meta: "当前活跃任务" },
        { label: "成功率", value: `${overview.metrics.success_rate.toFixed(2)}%`, meta: overview.metrics.build_backend },
        {
          label: "失败任务",
          value: overview.metrics.failed_tasks,
          meta: overview.metrics.build_ready ? "构建链路已就绪" : "构建环境待检查",
        },
      ]
    : [
        { label: "任务总数", value: "—", meta: "等待接口" },
        { label: "运行中", value: "—", meta: "等待接口" },
        { label: "成功率", value: "—", meta: "等待接口" },
        { label: "失败任务", value: "—", meta: "等待接口" },
      ];
  const failureDistribution = overview?.failure_distribution?.slice(0, 4) ?? [];
  const evaluationSummaries = overview?.evaluation_summaries ?? [];
  const maxFailureTotal = failureDistribution.reduce((max, item) => Math.max(max, item.total), 1);
  const recentEvents = overview?.events?.slice(0, 4) ?? [];
  const focusStats = [
    { label: "构建引擎", value: overview?.metrics.build_backend ?? "等待接口" },
    { label: "系统状态", value: overview?.metrics.build_ready ? "可执行" : overview ? "待检查" : "等待接口" },
    { label: "事件流", value: overview ? `${overview.events.length} 条` : "等待接口" },
  ];

  return (
    <div className="pw-overview">
      <SectionCard className="pw-overview-hero-card">
        <div className="pw-overview-hero pw-overview-hero-refined">
          <div className="pw-overview-hero-copy">
            <div className="pw-overview-eyebrow">{projectSummary.alias} / Livepatch Console</div>
            <h3 className="pw-overview-headline">{projectSummary.title}</h3>
            <p className="pw-overview-lead">{projectSummary.subtitle}</p>
            <div className="pw-pill-row">
              <span className="pw-chip">Anolis OS 23.4</span>
              <span className="pw-chip">kpatch-build</span>
              <span className="pw-chip">FastAPI + React</span>
              <span className="pw-chip">可回放证据</span>
            </div>
            <div className="pw-btn-row">
              <Link className="pw-btn primary" to="/tasks/new">
                创建任务
              </Link>
              <Link className="pw-btn" to="/reports">
                报告中心
              </Link>
              <Link className="pw-btn" to="/doctor">
                环境诊断
              </Link>
            </div>
            {overviewQuery.isLoading ? <div className="pw-note-banner">正在同步总览数据...</div> : null}
            {overviewQuery.isError ? <div className="pw-note-banner">当前无法连接后端，页面已回退到静态布局。</div> : null}
          </div>
          <aside className="pw-overview-focus-card">
            <span className="pw-overview-focus-kicker">Console Focus</span>
            <strong className="pw-overview-focus-title">把最关键的运行、排障与交付视图留在首屏</strong>
            <div className="pw-overview-focus-grid">
              {focusStats.map((item) => (
                <article key={item.label} className="pw-overview-focus-stat">
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </article>
              ))}
            </div>
            <div className="pw-overview-focus-track">
              {controlPlanes.map((item) => (
                <span key={item.title} className="pw-overview-focus-pill">
                  {item.title}
                </span>
              ))}
            </div>
          </aside>
        </div>
      </SectionCard>

      <div className="pw-overview-band">
        {runtimeStats.map((item) => (
          <article key={item.label} className="pw-runtime-card pw-runtime-card-band">
            <span className="pw-runtime-label">{item.label}</span>
            <strong className="pw-runtime-value">{item.value}</strong>
            <span className="pw-runtime-meta">{item.meta}</span>
          </article>
        ))}
      </div>

      <div className="pw-overview-grid">
        <div className="pw-overview-column pw-overview-column-main">
          <SectionCard title="任务队列" subtitle="最近任务、运行任务和失败任务统一从这里回看。" className="pw-overview-panel">
            {overview ? (
              <TaskTable items={overview.recent_tasks as TaskListItem[]} />
            ) : (
              <div className="pw-empty">后端可用后，这里会显示最近任务与当前状态。</div>
            )}
          </SectionCard>

          <SectionCard title="日志尾流" subtitle="保留系统层与构建层两条快速排障入口。" className="pw-overview-panel">
            {overview ? (
              <div className="pw-log-grid pw-log-grid-wide">
                <div className="pw-log-card">
                  <span className="pw-log-label">system_log</span>
                  <pre className="pw-code-content pw-code-compact">{overview.logs_tail.system_log.lines.join("\n") || "暂无日志"}</pre>
                </div>
                <div className="pw-log-card">
                  <span className="pw-log-label">latest_build_log</span>
                  <pre className="pw-code-content pw-code-compact">
                    {overview.logs_tail.latest_build_log?.lines.join("\n") || "暂无构建日志"}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="pw-empty">后端可用后，这里会展示最近 system/build log 片段。</div>
            )}
          </SectionCard>
        </div>

        <div className="pw-overview-column pw-overview-column-side">
          <SectionCard title="异常信号" subtitle="按 failure_type 聚合最近失败，用于快速识别风险热点。" className="pw-overview-panel">
            {failureDistribution.length ? (
              <div className="pw-signal-stack">
                {failureDistribution.map((item) => (
                  <div key={item.failure_type} className="pw-signal-meter">
                    <div className="pw-signal-meter-copy">
                      <strong>{item.failure_type}</strong>
                      <span>{item.total} 次</span>
                    </div>
                    <div className="pw-signal-meter-bar">
                      <span style={{ width: `${(item.total / maxFailureTotal) * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="pw-empty">暂无失败分布。</div>
            )}
          </SectionCard>

          <SectionCard
            title="固定样例评测"
            subtitle="直接联到报告中心中的分组摘要，便于阶段汇报与封版核对。"
            className="pw-overview-panel"
          >
            {evaluationSummaries.length ? (
              <div className="pw-list">
                {evaluationSummaries.map((item) => (
                  <Link
                    key={item.fixture_name}
                    className="pw-list-item pw-link-card"
                    to={`/reports/fixtures/${toFixtureGroupPath(item.fixture_name)}`}
                  >
                    <strong>{item.fixture_name}</strong>
                    <div className="pw-inline-note">
                      成功 {item.success_count}/{item.matched_fixtures}，成功率 {(item.success_rate * 100).toFixed(2)}%
                    </div>
                    <div className="pw-inline-note">
                      样例 {item.total_fixtures}，缺失 {item.missing_fixtures}，平均尝试 {item.average_attempts}
                    </div>
                    <div className="pw-inline-note">摘要路径: {shortenPath(item.summary_json_path)}</div>
                    <div className="pw-inline-note">更新时间: {formatTime(item.updated_at)}</div>
                  </Link>
                ))}
              </div>
            ) : (
              <div className="pw-empty">当前还没有固定样例摘要，执行评测后这里会自动汇总。</div>
            )}
          </SectionCard>

          <SectionCard title="最近事件" subtitle="保留任务级动态，便于答辩时快速定位。" className="pw-overview-panel">
            {recentEvents.length ? (
              <div className="pw-event-feed">
                {recentEvents.map((item) => (
                  <article key={`${item.kind}-${item.timestamp}-${item.title}`} className="pw-event-feed-item">
                    <div className="pw-event-feed-meta">
                      <span className="pw-event-kind">{item.kind}</span>
                      <span>{formatTime(item.timestamp)}</span>
                    </div>
                    <strong>{item.title}</strong>
                  </article>
                ))}
              </div>
            ) : (
              <div className="pw-empty">暂无事件流。</div>
            )}
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
