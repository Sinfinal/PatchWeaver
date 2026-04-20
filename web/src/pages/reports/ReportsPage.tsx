import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { MetricCard } from "../../components/cards/MetricCard";
import { SectionCard } from "../../components/layout/SectionCard";
import { StatusBadge } from "../../components/status/StatusBadge";
import { reportGroupGuides, reportHighlights } from "../../content/projectContent";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { fetchEvaluationGroups } from "../../services/reports";
import { fetchTasks } from "../../services/tasks";
import { formatPercent, formatTime, shortenPath } from "../../utils/format";

export function ReportsPage(): JSX.Element {
  const liveQueryOptions = useLiveQueryOptions();
  const groupsQuery = useQuery({
    queryKey: ["report-groups"],
    queryFn: fetchEvaluationGroups,
    ...liveQueryOptions,
  });
  const tasksQuery = useQuery({
    queryKey: ["report-recent-tasks"],
    queryFn: () => fetchTasks({ limit: 8 }),
    ...liveQueryOptions,
  });

  const groups = groupsQuery.data?.items ?? [];
  const recentTasks = tasksQuery.data?.items ?? [];
  const stageStats = useMemo(() => {
    const totalFixtures = groups.reduce((total, item) => total + item.total_fixtures, 0);
    const matchedFixtures = groups.reduce((total, item) => total + item.matched_fixtures, 0);
    const successCount = groups.reduce((total, item) => total + item.success_count, 0);
    const missingFixtures = groups.reduce((total, item) => total + item.missing_fixtures, 0);
    const weightedAttempts = groups.reduce((total, item) => total + item.average_attempts * item.matched_fixtures, 0);
    return {
      totalFixtures,
      matchedFixtures,
      successCount,
      missingFixtures,
      successRate: matchedFixtures > 0 ? successCount / matchedFixtures : 0,
      averageAttempts: matchedFixtures > 0 ? weightedAttempts / matchedFixtures : 0,
    };
  }, [groups]);

  return (
    <div className="pw-grid">
      <SectionCard title="报告中心" subtitle="围绕任务报告、固定样例和阶段统计组织统一的回看入口。">
        <div className="pw-highlight-grid">
          {reportHighlights.map((item) => (
            <div key={item.title} className="pw-mini-card">
              <strong>{item.title}</strong>
              <div className="pw-inline-note">{item.description}</div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="阶段统计" subtitle="按当前已有评测分组汇总首屏指标，用于阶段汇报和演示核对。">
        <div className="pw-grid metrics">
          <MetricCard label="评测分组" value={groups.length} />
          <MetricCard label="样例总数" value={stageStats.totalFixtures} />
          <MetricCard label="已匹配样例" value={stageStats.matchedFixtures} />
          <MetricCard label="成功率" value={formatPercent(stageStats.successRate)} />
          <MetricCard label="缺失样例" value={stageStats.missingFixtures} />
          <MetricCard label="平均尝试轮次" value={stageStats.averageAttempts.toFixed(2)} />
        </div>
      </SectionCard>

      <div className="pw-grid two">
        <SectionCard title="任务报告" subtitle="优先从这里进入任务级报告页，集中查看 report、验证和回放摘要。">
          {tasksQuery.isLoading ? <div className="pw-note-banner">正在加载任务清单...</div> : null}
          {tasksQuery.isError ? <div className="pw-note-banner">当前无法读取任务清单，稍后重试即可。</div> : null}
          {recentTasks.length > 0 ? (
            <div className="pw-list">
              {recentTasks.map((task) => (
                <Link key={task.task_id} className="pw-list-item pw-link-card" to={`/reports/tasks/${task.task_id}`}>
                  <strong>
                    {task.task_id} · {task.cve_id}
                  </strong>
                  <div className="pw-report-inline">
                    <StatusBadge value={task.status} />
                    <span className="pw-inline-note">
                      第 {task.current_attempt}/{task.max_attempts} 轮
                    </span>
                  </div>
                  <div className="pw-inline-note">{task.target_kernel}</div>
                  <div className="pw-inline-note">最近更新时间：{formatTime(task.updated_at)}</div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="pw-empty">当前还没有任务报告可展示。</div>
          )}
        </SectionCard>

        <SectionCard title="固定样例分组" subtitle="分组页负责展示 summary.json、summary.md 和单样例入口。">
          {groupsQuery.isLoading ? <div className="pw-note-banner">正在扫描评测分组...</div> : null}
          {groupsQuery.isError ? <div className="pw-note-banner">当前无法读取评测分组，请确认 data/evaluations 是否已有结果。</div> : null}
          {groups.length > 0 ? (
            <div className="pw-list">
              {groups.map((group) => (
                <Link key={group.group_id} className="pw-list-item pw-link-card" to={`/reports/fixtures/${group.group_id}`}>
                  <strong>{group.display_name}</strong>
                  <div className="pw-inline-note">
                    成功 {group.success_count}/{group.matched_fixtures}，成功率 {formatPercent(group.success_rate)}
                  </div>
                  <div className="pw-inline-note">
                    样例 {group.total_fixtures}，缺失 {group.missing_fixtures}，平均尝试 {group.average_attempts.toFixed(2)}
                  </div>
                  <div className="pw-inline-note">摘要路径：{shortenPath(group.summary_json_path)}</div>
                  <div className="pw-inline-note">更新时间：{formatTime(group.updated_at)}</div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="pw-empty">当前还没有固定样例结果目录。</div>
          )}
        </SectionCard>
      </div>

      <SectionCard title="分组口径说明" subtitle="这里保留文档中的常用分组口径，避免联调和汇报时口径混淆。">
        <div className="pw-highlight-grid">
          {reportGroupGuides.map((item) => (
            <div key={item.title} className="pw-mini-card">
              <strong>{item.title}</strong>
              <div className="pw-inline-note">{item.description}</div>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
