import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { TaskCreateForm } from "../../components/forms/TaskCreateForm";
import { SectionCard } from "../../components/layout/SectionCard";
import { TaskTable } from "../../components/tables/TaskTable";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { createTask, fetchTasks } from "../../services/tasks";
import type { CreateTaskPayload } from "../../types/tasks";

const PAGE_SIZE_OPTIONS = [20, 50, 100] as const;

export function TaskListPage(): JSX.Element {
  const navigate = useNavigate();
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>(20);
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
    queryKey: ["tasks", filters, page, pageSize],
    queryFn: () =>
      fetchTasks({
        limit: pageSize,
        offset: (page - 1) * pageSize,
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
  const pagination = tasksQuery.data;
  const pageCount = pagination?.page_count ?? 1;
  const pageStart = pagination && pagination.total > 0 ? pagination.offset + 1 : 0;
  const pageEnd = pagination ? Math.min(pagination.offset + pagination.items.length, pagination.total) : 0;

  useEffect(() => {
    if (tasksQuery.data && page > tasksQuery.data.page_count) {
      setPage(tasksQuery.data.page_count);
    }
  }, [page, tasksQuery.data]);

  const updateFilter = (key: keyof typeof filters, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  };

  const updatePageSize = (value: string) => {
    setPageSize(Number(value) as (typeof PAGE_SIZE_OPTIONS)[number]);
    setPage(1);
  };

  const createMutation = useMutation({
    mutationFn: (payload: CreateTaskPayload) => createTask(payload),
    onSuccess: (data) => {
      const targetTask = data.task ?? data.existing_task;
      setCreateDialogOpen(false);
      if (targetTask?.task_id) {
        navigate(`/tasks/${targetTask.task_id}`);
      }
    },
  });
  const closeCreateDialog = () => {
    createMutation.reset();
    setCreateDialogOpen(false);
  };

  return (
    <div className="pw-grid">
      <SectionCard
        title="任务中心"
        actions={
          <button className="pw-btn primary" type="button" onClick={() => setCreateDialogOpen(true)}>
            创建任务
          </button>
        }
      >
        <div className="pw-grid two" style={{ marginBottom: 18 }}>
          <input
            className="pw-input"
            placeholder="按 CVE 编号搜索，例如 CVE-2024-1086"
            value={filters.cve_id}
            onChange={(event) => updateFilter("cve_id", event.target.value)}
          />
          <input
            className="pw-input"
            placeholder="按状态筛选，例如 running / failed / built / reported"
            value={filters.status}
            onChange={(event) => updateFilter("status", event.target.value)}
          />
          <input
            className="pw-input"
            type="datetime-local"
            title="创建时间起始"
            value={filters.created_at_from}
            onChange={(event) => updateFilter("created_at_from", event.target.value)}
          />
          <input
            className="pw-input"
            type="datetime-local"
            title="创建时间截止"
            value={filters.created_at_to}
            onChange={(event) => updateFilter("created_at_to", event.target.value)}
          />
        </div>
        {tasksQuery.isLoading ? (
          <div className="pw-note-banner">正在加载任务列表...</div>
        ) : tasksQuery.isError || !tasksQuery.data ? (
          <div className="pw-empty">当前无法获取任务列表，请确认后端 API 已启动</div>
        ) : (
          <div className="pw-section-stack">
            <div className="pw-pagination">
              <div className="pw-pagination-summary">
                共 {tasksQuery.data.total} 条，当前显示 {pageStart}-{pageEnd}，第 {tasksQuery.data.page}/{pageCount} 页
              </div>
              <div className="pw-pagination-controls" aria-label="任务分页">
                <label className="pw-pagination-size">
                  每页
                  <select className="pw-select pw-select-inline" value={pageSize} onChange={(event) => updatePageSize(event.target.value)}>
                    {PAGE_SIZE_OPTIONS.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </label>
                <button className="pw-btn" type="button" onClick={() => setPage(1)} disabled={!tasksQuery.data.has_prev}>
                  首页
                </button>
                <button className="pw-btn" type="button" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={!tasksQuery.data.has_prev}>
                  上一页
                </button>
                <button className="pw-btn" type="button" onClick={() => setPage((current) => Math.min(pageCount, current + 1))} disabled={!tasksQuery.data.has_next}>
                  下一页
                </button>
                <button className="pw-btn" type="button" onClick={() => setPage(pageCount)} disabled={!tasksQuery.data.has_next}>
                  末页
                </button>
              </div>
            </div>
            <TaskTable items={tasksQuery.data.items} />
          </div>
        )}
      </SectionCard>
      {createDialogOpen ? (
        <div className="pw-modal-backdrop" role="presentation" onMouseDown={closeCreateDialog}>
          <section
            className="pw-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="task-create-dialog-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="pw-modal-header">
              <div>
                <span className="pw-kicker">Task Launch</span>
                <h3 id="task-create-dialog-title">创建任务</h3>
              </div>
              <button
                className="pw-icon-btn"
                type="button"
                aria-label="关闭创建任务弹窗"
                onClick={closeCreateDialog}
              >
                ×
              </button>
            </div>
            <TaskCreateForm submitting={createMutation.isPending} onSubmit={createMutation.mutateAsync} />
            {createMutation.isError ? <div className="pw-empty">任务创建失败，请检查后端返回的错误信息或配置状态</div> : null}
          </section>
        </div>
      ) : null}
    </div>
  );
}
