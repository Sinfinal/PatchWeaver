import { useQuery } from "@tanstack/react-query";
import { MetricCard } from "../../components/cards/MetricCard";
import { SectionCard } from "../../components/layout/SectionCard";
import { TaskTable } from "../../components/tables/TaskTable";
import { fetchOverview } from "../../services/overview";
import type { TaskListItem } from "../../types/tasks";

export function OverviewPage(): JSX.Element {
  const overviewQuery = useQuery({
    queryKey: ["overview"],
    queryFn: fetchOverview,
  });

  if (overviewQuery.isLoading) {
    return <div className="pw-empty">总览数据加载中...</div>;
  }

  if (overviewQuery.isError || !overviewQuery.data) {
    return <div className="pw-empty">总览数据加载失败。</div>;
  }

  const { metrics, recent_tasks, failure_distribution, events, logs_tail } = overviewQuery.data;

  return (
    <div className="pw-grid">
      <SectionCard title="运行概览" subtitle="任务状态、构建后端和失败分布的首屏快照">
        <div className="pw-grid metrics">
          <MetricCard label="总任务数" value={metrics.total_tasks} />
          <MetricCard label="运行中任务" value={metrics.running_tasks} />
          <MetricCard label="成功任务" value={metrics.success_tasks} />
          <MetricCard label="失败任务" value={metrics.failed_tasks} />
          <MetricCard label="验证通过" value={metrics.validation_passed} />
          <MetricCard label="验证失败" value={metrics.validation_failed} />
          <MetricCard label="成功率" value={`${metrics.success_rate}%`} />
          <MetricCard
            label="构建后端"
            value={metrics.build_backend}
            meta={metrics.build_ready ? "当前后端已通过关键预检" : "当前后端仍有预检缺项"}
          />
        </div>
      </SectionCard>

      <div className="pw-grid two">
        <SectionCard title="最近任务" subtitle="点击行可进入详情页">
          <TaskTable items={recent_tasks as TaskListItem[]} />
        </SectionCard>
        <SectionCard title="失败类型分布" subtitle="按 failure_record 聚合">
          {failure_distribution.length > 0 ? (
            <div className="pw-list">
              {failure_distribution.map((item) => (
                <div key={item.failure_type} className="pw-list-item">
                  <strong>{item.failure_type}</strong>
                  <span className="pw-inline-note">累计 {item.total} 次</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="pw-empty">当前还没有失败归因记录。</div>
          )}
        </SectionCard>
      </div>

      <div className="pw-grid two">
        <SectionCard title="验证结果分布" subtitle="按 validation_record 聚合">
          {overviewQuery.data.validation_distribution.length > 0 ? (
            <div className="pw-list">
              {overviewQuery.data.validation_distribution.map((item) => (
                <div key={item.status} className="pw-list-item">
                  <strong>{item.status}</strong>
                  <span className="pw-inline-note">累计 {item.total} 次</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="pw-empty">当前还没有验证结果记录。</div>
          )}
        </SectionCard>
        <SectionCard title="最近阶段评测" subtitle="固定样例评测输出的最新摘要路径">
          <div className="pw-list">
            <div className="pw-list-item">
              <strong>评测摘要路径</strong>
              <div className="pw-inline-note">{metrics.latest_evaluation_summary ?? "当前还没有阶段评测摘要。"}</div>
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="pw-grid two">
        <SectionCard title="近期事件" subtitle="任务、尝试轮和失败归因统一汇总">
          {events.length > 0 ? (
            <div className="pw-list">
              {events.map((item) => (
                <div key={`${item.kind}-${item.timestamp}-${item.title}`} className="pw-list-item">
                  <strong>{item.title}</strong>
                  <div className="pw-inline-note">{item.timestamp}</div>
                  <div className="pw-inline-note">{item.detail}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="pw-empty">当前没有可展示的事件。</div>
          )}
        </SectionCard>
        <SectionCard title="日志尾流" subtitle="系统日志与最近构建日志的尾部内容">
          <div className="pw-list">
            <div className="pw-list-item">
              <strong>系统日志</strong>
              <div className="pw-inline-note">{logs_tail.paths.system_log}</div>
              <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 220 }}>
                {logs_tail.system_log.lines.join("\n") || "当前没有系统日志。"}
              </pre>
            </div>
            <div className="pw-list-item">
              <strong>最近构建日志</strong>
              <div className="pw-inline-note">{logs_tail.paths.latest_build_log ?? "暂无路径"}</div>
              <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 220 }}>
                {logs_tail.latest_build_log?.lines.join("\n") || "当前没有构建日志。"}
              </pre>
            </div>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
