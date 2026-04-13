import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { SectionCard } from "../../components/layout/SectionCard";
import { TaskTable } from "../../components/tables/TaskTable";
import { fetchTasks } from "../../services/tasks";

export function TaskListPage(): JSX.Element {
  const [filters, setFilters] = useState({
    cve_id: "",
    status: "",
    failure_type: "",
    target_kernel: "",
  });

  const queryParams = useMemo(() => ({ limit: 80, ...filters }), [filters]);
  const tasksQuery = useQuery({
    queryKey: ["tasks", queryParams],
    queryFn: () => fetchTasks(queryParams),
  });

  return (
    <div className="pw-grid">
      <SectionCard
        title="任务列表"
        subtitle="集中查看 CVE 任务、尝试轮次和最近失败类型"
        actions={
          <Link className="pw-btn primary" to="/tasks/new">
            新建任务
          </Link>
        }
      >
        <div className="pw-grid two" style={{ marginBottom: 18 }}>
          <input
            className="pw-input"
            placeholder="按 CVE 检索"
            value={filters.cve_id}
            onChange={(event) => setFilters((current) => ({ ...current, cve_id: event.target.value }))}
          />
          <input
            className="pw-input"
            placeholder="按状态筛选，例如 failed"
            value={filters.status}
            onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}
          />
          <input
            className="pw-input"
            placeholder="按失败类型筛选"
            value={filters.failure_type}
            onChange={(event) => setFilters((current) => ({ ...current, failure_type: event.target.value }))}
          />
          <input
            className="pw-input"
            placeholder="按目标内核筛选"
            value={filters.target_kernel}
            onChange={(event) => setFilters((current) => ({ ...current, target_kernel: event.target.value }))}
          />
        </div>
        {tasksQuery.isLoading ? (
          <div className="pw-empty">任务列表加载中...</div>
        ) : tasksQuery.isError || !tasksQuery.data ? (
          <div className="pw-empty">任务列表加载失败。</div>
        ) : (
          <TaskTable items={tasksQuery.data.items} />
        )}
      </SectionCard>
    </div>
  );
}
