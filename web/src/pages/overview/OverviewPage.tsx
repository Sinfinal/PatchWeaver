import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { SectionCard } from "../../components/layout/SectionCard";
import { TaskTable } from "../../components/tables/TaskTable";
import { controlPlanes, projectSummary } from "../../content/projectContent";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { fetchOverview } from "../../services/overview";
import type { TaskListItem } from "../../types/tasks";
import { failureSignalMeaning } from "../../utils/failureSignals";
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
    { label: "构建状态", value: overview?.metrics.build_ready ? "可执行" : overview ? "待检查" : "等待接口" },
    { label: "交付状态", value: overview?.metrics.delivery_ready ? "已就绪" : overview ? "待准备" : "等待接口" },
    { label: "默认模型", value: overview?.metrics.selected_model ?? "等待接口" },
    { label: "事件流", value: overview ? `${overview.events.length} 条` : "等待接口" },
  ];

  return (
    <div className="pw-overview">
      <SectionCard className="pw-overview-hero-card">
        <div className="pw-overview-hero pw-overview-hero-refined">
          <div className="pw-overview-hero-copy">
            <div className="pw-overview-eyebrow">{projectSummary.alias} / Livepatch Console</div>
            <h3 className="pw-overview-headline">{projectSummary.title}</h3>
            {projectSummary.subtitle ? <p className="pw-overview-lead">{projectSummary.subtitle}</p> : null}
            <div className="pw-pill-row">
              <span className="pw-chip">Anolis OS 23.4</span>
              <span className="pw-chip">kpatch-build</span>
              <span className="pw-chip">FastAPI + React</span>
              <span className="pw-chip">可回放证据</span>
            </div>
            <div className="pw-btn-row">
              <Link className="pw-btn primary" to="/tasks">
                任务中心
              </Link>
              <Link className="pw-btn" to="/reports">
                报告中心
              </Link>
              <Link className="pw-btn" to="/doctor">
                环境诊断
              </Link>
            </div>
            {overviewQuery.isLoading ? <div className="pw-note-banner">正在同步总览数据...</div> : null}
            {overviewQuery.isError ? <div className="pw-note-banner">当前无法连接后端，页面已回退到静态布局</div> : null}
          </div>
          <aside className="pw-overview-focus-card">
            <span className="pw-overview-focus-kicker">执行状态</span>
            <strong className="pw-overview-focus-title">任务状态 / 失败归因 / 验证证据</strong>
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
        <SectionCard title="任务队列" className="pw-overview-panel pw-overview-panel-task">
          {overview ? (
            <TaskTable items={overview.recent_tasks as TaskListItem[]} />
          ) : (
            <div className="pw-empty">后端可用后，这里会显示最近任务与当前状态</div>
          )}
        </SectionCard>

        <SectionCard title="异常信号" className="pw-overview-panel pw-overview-panel-signal">
          {failureDistribution.length ? (
            <div className="pw-signal-stack">
              {failureDistribution.map((item) => (
                <div key={item.failure_type} className="pw-signal-meter">
                  <div className="pw-signal-meter-copy">
                    <strong>{item.failure_type}</strong>
                    <span>{item.total} 次</span>
                  </div>
                  <div className="pw-signal-meter-meaning">含义：{failureSignalMeaning(item)}</div>
                  <div className="pw-signal-meter-bar">
                    <span style={{ width: `${(item.total / maxFailureTotal) * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="pw-empty">暂无失败分布</div>
          )}
        </SectionCard>

        <SectionCard
          title="固定样例评测"
          className="pw-overview-panel pw-overview-panel-evaluation"
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
            <div className="pw-empty">当前还没有固定样例摘要，执行评测后这里会自动汇总</div>
          )}
        </SectionCard>

        <SectionCard title="封版交付" className="pw-overview-panel pw-overview-panel-release">
          {overview ? (
            <div className="pw-list">
              <div className="pw-list-item">
                <strong>门禁状态</strong>
                <div className="pw-inline-note">{overview.release.final_gate_status ?? "未执行 gate"}</div>
              </div>
              <div className="pw-list-item">
                <strong>final_manifest</strong>
                <div className="pw-inline-note">{shortenPath(overview.release.final_manifest_path ?? "未生成")}</div>
              </div>
              <div className="pw-list-item">
                <strong>submission 根目录</strong>
                <div className="pw-inline-note">{shortenPath(overview.release.submission_root)}</div>
              </div>
              <div className="pw-list-item">
                <strong>模型口径</strong>
                <div className="pw-inline-note">
                  主模型 {overview.release.selected_models.primary_model} / 交付 {overview.release.selected_models.delivery_model}
                </div>
                <div className="pw-inline-note">拓扑: {overview.release.selected_models.topology}</div>
                <div className="pw-inline-note">
                  辅助:{" "}
                  {Object.entries(overview.release.selected_models.helper_models).length
                    ? Object.entries(overview.release.selected_models.helper_models)
                        .map(([name, model]) => `${name}=${model}`)
                        .join("，")
                    : "未配置"}
                </div>
              </div>
            </div>
          ) : (
            <div className="pw-empty">后端可用后，这里会展示 final manifest 和最终门禁状态</div>
          )}
        </SectionCard>

        <SectionCard title="日志尾流" className="pw-overview-panel pw-overview-panel-logs">
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
            <div className="pw-empty">后端可用后，这里会展示最近 system/build log 片段</div>
          )}
        </SectionCard>

        <SectionCard title="最近事件" className="pw-overview-panel pw-overview-panel-events">
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
            <div className="pw-empty">暂无事件流</div>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
