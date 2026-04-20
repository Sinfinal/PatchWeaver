import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { SectionCard } from "../../components/layout/SectionCard";
import { TaskTable } from "../../components/tables/TaskTable";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { fetchTasks } from "../../services/tasks";

export function TaskListPage(): JSX.Element {
  const [filters, setFilters] = useState({
    cve_id: "",
    status: "",
    failure_type: "",
    target_kernel: "",
  });

  const liveQueryOptions = useLiveQueryOptions();
  const tasksQuery = useQuery({
    queryKey: ["tasks", filters],
    queryFn: () => fetchTasks({ limit: 80, ...filters }),
    ...liveQueryOptions,
  });

  return (
    <div className="pw-grid">
      <SectionCard
        title="任务中心"
        subtitle="围绕 CVE、状态、失败类型和目标内核做快速过滤，并直接跳入任务详情。"
        actions={
          <Link className="pw-btn primary" to="/tasks/new">
            创建任务
          </Link>
        }
      >
        <div className="pw-grid two" style={{ marginBottom: 18 }}>
          <input
            className="pw-input"
            placeholder="按 CVE 过滤，例如 CVE-2024-1086"
            value={filters.cve_id}
            onChange={(event) => setFilters((current) => ({ ...current, cve_id: event.target.value }))}
          />
          <input
            className="pw-input"
            placeholder="按状态过滤，例如 running / failed / reported"
            value={filters.status}
            onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}
          />
          <input
            className="pw-input"
            placeholder="按失败类型过滤，例如 patch_apply_failed"
            value={filters.failure_type}
            onChange={(event) => setFilters((current) => ({ ...current, failure_type: event.target.value }))}
          />
          <input
            className="pw-input"
            placeholder="按目标内核过滤，例如 6.6.102-5.2.an23.x86_64"
            value={filters.target_kernel}
            onChange={(event) => setFilters((current) => ({ ...current, target_kernel: event.target.value }))}
          />
        </div>
        {tasksQuery.isLoading ? (
          <div className="pw-note-banner">正在加载任务列表...</div>
        ) : tasksQuery.isError || !tasksQuery.data ? (
          <div className="pw-empty">当前无法获取任务列表，请确认后端 API 已启动。</div>
        ) : (
          <div className="pw-section-stack">
            <div className="pw-inline-note">共返回 {tasksQuery.data.total} 条任务记录。</div>
            <TaskTable items={tasksQuery.data.items} />
          </div>
        )}
      </SectionCard>
    </div>
  );
}
