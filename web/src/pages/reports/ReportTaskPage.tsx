import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { CodePanel } from "../../components/code/CodePanel";
import { SectionCard } from "../../components/layout/SectionCard";
import { StatusBadge } from "../../components/status/StatusBadge";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { fetchTaskReport } from "../../services/reports";
import { formatTime, shortenPath } from "../../utils/format";

export function ReportTaskPage(): JSX.Element {
  const params = useParams<{ taskId: string }>();
  const taskId = params.taskId ?? "";
  const liveQueryOptions = useLiveQueryOptions();
  const query = useQuery({
    queryKey: ["task-report", taskId],
    queryFn: () => fetchTaskReport(taskId),
    enabled: taskId.length > 0,
    ...liveQueryOptions,
  });

  if (query.isLoading) {
    return <div className="pw-empty">正在加载任务报告...</div>;
  }

  if (query.isError || !query.data) {
    return <div className="pw-empty">当前无法获取任务报告，请确认任务编号和报告产物是否存在</div>;
  }

  const payload = query.data;

  return (
    <div className="pw-grid">
      <SectionCard
        title={payload.task.task_id}
        actions={
          <div className="pw-btn-row">
            <Link className="pw-btn" to={`/tasks/${payload.task.task_id}`}>
              打开任务详情
            </Link>
          </div>
        }
      >
        <div className="pw-kv">
          <div className="pw-kv-item">
            <span className="pw-kv-label">任务状态</span>
            <div className="pw-kv-value">
              <StatusBadge value={payload.task.status} />
            </div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">目标内核</span>
            <div className="pw-kv-value">{payload.task.target_kernel}</div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">尝试轮次</span>
            <div className="pw-kv-value">
              {payload.task.current_attempt}/{payload.task.max_attempts}
            </div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">创建时间</span>
            <div className="pw-kv-value">{formatTime(payload.task.created_at)}</div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">report.json</span>
            <div className="pw-kv-value">{shortenPath(payload.report.json_path)}</div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">report.md</span>
            <div className="pw-kv-value">{shortenPath(payload.report.md_path)}</div>
          </div>
        </div>
      </SectionCard>

      {payload.agent_decision_summary ? (
        <SectionCard title="智能体决策摘要">
          <div className="pw-kv">
            <div className="pw-kv-item">
              <span className="pw-kv-label">RepairIntent 策略</span>
              <div className="pw-kv-value">{payload.agent_decision_summary.strategy_switch.repair_intent_strategy ?? "未记录"}</div>
            </div>
            <div className="pw-kv-item">
              <span className="pw-kv-label">选中 Recipe</span>
              <div className="pw-kv-value">{payload.agent_decision_summary.selected_recipe ?? "未记录"}</div>
            </div>
            <div className="pw-kv-item">
              <span className="pw-kv-label">最终策略</span>
              <div className="pw-kv-value">{payload.agent_decision_summary.strategy ?? "未记录"}</div>
            </div>
            <div className="pw-kv-item">
              <span className="pw-kv-label">失败类型</span>
              <div className="pw-kv-value">{payload.agent_decision_summary.failure_type ?? "无"}</div>
            </div>
            <div className="pw-kv-item">
              <span className="pw-kv-label">下一步动作</span>
              <div className="pw-kv-value">{payload.agent_decision_summary.agent_next_action ?? "未记录"}</div>
            </div>
            <div className="pw-kv-item">
              <span className="pw-kv-label">FailureRecord</span>
              <div className="pw-kv-value">{shortenPath(payload.agent_decision_summary.source_paths.failure_record)}</div>
            </div>
          </div>
        </SectionCard>
      ) : null}

      <div className="pw-grid two">
        <SectionCard title="Markdown 报告">
          <CodePanel
            title="report.md"
            path={payload.report.md_path}
            content={payload.report.markdown ?? undefined}
            emptyText="当前还没有 report.md 内容"
          />
        </SectionCard>
        <SectionCard title="JSON 报告">
          <CodePanel
            title="report.json"
            path={payload.report.json_path}
            content={payload.report.json ? JSON.stringify(payload.report.json, null, 2) : undefined}
            emptyText="当前还没有 report.json 内容"
          />
        </SectionCard>
      </div>

      <div className="pw-grid two">
        <SectionCard title="最新失败记录">
          <CodePanel
            title="latest_failure"
            content={payload.latest_failure ? JSON.stringify(payload.latest_failure, null, 2) : undefined}
            emptyText="当前没有 failure_record"
          />
        </SectionCard>
        <SectionCard title="最新验证结果">
          <CodePanel
            title="latest_validation"
            content={payload.latest_validation ? JSON.stringify(payload.latest_validation, null, 2) : undefined}
            emptyText="当前没有 validation_report"
          />
        </SectionCard>
      </div>

      <div className="pw-grid two">
        <SectionCard title="阶段评测摘要">
          <CodePanel
            title="evaluation_summary"
            content={payload.evaluation_summary ? JSON.stringify(payload.evaluation_summary, null, 2) : undefined}
            emptyText="当前没有 evaluation_summary"
          />
        </SectionCard>
        <SectionCard title="回放摘要">
          <CodePanel title="replay" content={JSON.stringify(payload.replay, null, 2)} emptyText="当前没有 replay 内容" />
        </SectionCard>
      </div>
    </div>
  );
}
