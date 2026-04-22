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
    build_exec_status: "",
    target_state: "",
    fixture_group: "",
    created_at_from: "",
    created_at_to: "",
    current_attempt: "",
  });

  const liveQueryOptions = useLiveQueryOptions();
  const tasksQuery = useQuery({
    queryKey: ["tasks", filters],
    queryFn: () =>
      fetchTasks({
        limit: 80,
        cve_id: filters.cve_id || undefined,
        status: filters.status || undefined,
        failure_type: filters.failure_type || undefined,
        target_kernel: filters.target_kernel || undefined,
        build_exec_status: filters.build_exec_status || undefined,
        target_state: filters.target_state || undefined,
        fixture_group: filters.fixture_group || undefined,
        created_at_from: filters.created_at_from || undefined,
        created_at_to: filters.created_at_to || undefined,
        current_attempt: filters.current_attempt ? Number(filters.current_attempt) : undefined,
      }),
    ...liveQueryOptions,
  });

  return (
    <div className="pw-grid">
      <SectionCard
        title="任务中心"
        subtitle="围绕 CVE、状态、失败类型、构建执行态、样例分组和时间范围做快速筛选，并直接跳入任务详情。"
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
          <input
            className="pw-input"
            placeholder="按构建执行态过滤，例如 executed / not_run"
            value={filters.build_exec_status}
            onChange={(event) => setFilters((current) => ({ ...current, build_exec_status: event.target.value }))}
          />
          <input
            className="pw-input"
            placeholder="按目标态过滤，例如 target_already_patched"
            value={filters.target_state}
            onChange={(event) => setFilters((current) => ({ ...current, target_state: event.target.value }))}
          />
          <input
            className="pw-input"
            placeholder="按固定样例分组过滤，例如 challenge_dev / holdout"
            value={filters.fixture_group}
            onChange={(event) => setFilters((current) => ({ ...current, fixture_group: event.target.value }))}
          />
          <input
            className="pw-input"
            type="number"
            min={0}
            placeholder="按当前尝试轮过滤，例如 1"
            value={filters.current_attempt}
            onChange={(event) => setFilters((current) => ({ ...current, current_attempt: event.target.value }))}
          />
          <input
            className="pw-input"
            type="datetime-local"
            value={filters.created_at_from}
            onChange={(event) => setFilters((current) => ({ ...current, created_at_from: event.target.value }))}
          />
          <input
            className="pw-input"
            type="datetime-local"
            value={filters.created_at_to}
            onChange={(event) => setFilters((current) => ({ ...current, created_at_to: event.target.value }))}
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
