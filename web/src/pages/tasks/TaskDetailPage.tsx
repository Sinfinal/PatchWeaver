import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { CodePanel } from "../../components/code/CodePanel";
import { SectionCard } from "../../components/layout/SectionCard";
import { StatusBadge } from "../../components/status/StatusBadge";
import { StageTimeline, stageLabelMap } from "../../components/timeline/StageTimeline";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { useTaskEvents } from "../../hooks/useTaskEvents";
import {
  analyzeTask,
  fetchArtifactContent,
  fetchArtifacts,
  fetchTaskDetail,
  reportTask,
  runTask,
} from "../../services/tasks";
import { useUiStore } from "../../store/uiStore";
import { copyText, formatTime, shortenPath } from "../../utils/format";
import type { TaskAttempt, TaskDetailResponse } from "../../types/tasks";

type TabKey = "overview" | "input" | "analysis" | "attempts" | "build" | "validate" | "report" | "replay" | "artifacts";

const FILE_PAGE_SIZE = 12;

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "overview", label: "概览" },
  { key: "input", label: "输入" },
  { key: "analysis", label: "分析" },
  { key: "attempts", label: "尝试轮" },
  { key: "build", label: "构建" },
  { key: "validate", label: "验证" },
  { key: "report", label: "报告" },
  { key: "replay", label: "回放" },
  { key: "artifacts", label: "产物" },
];

export function TaskDetailPage(): JSX.Element {
  const params = useParams<{ taskId: string }>();
  const taskId = params.taskId ?? "";
  const queryClient = useQueryClient();
  const liveQueryOptions = useLiveQueryOptions();
  const selectedAttemptNo = useUiStore((state) => state.selectedAttemptNo);
  const setSelectedAttemptNo = useUiStore((state) => state.setSelectedAttemptNo);
  const [selectedTab, setSelectedTab] = useState<TabKey>("overview");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [filePage, setFilePage] = useState(1);
  const refreshTaskDetail = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
    queryClient.invalidateQueries({ queryKey: ["task-artifacts", taskId] });
    queryClient.invalidateQueries({ queryKey: ["overview"] });
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["task-report", taskId] });
    if (selectedPath) {
      queryClient.invalidateQueries({ queryKey: ["artifact-content", taskId, selectedPath] });
    }
  }, [queryClient, selectedPath, taskId]);
  const liveEventStatus = useTaskEvents(taskId, refreshTaskDetail);

  const detailQuery = useQuery({
    queryKey: ["task-detail", taskId],
    queryFn: () => fetchTaskDetail(taskId),
    enabled: taskId.length > 0,
    ...liveQueryOptions,
  });
  const artifactsQuery = useQuery({
    queryKey: ["task-artifacts", taskId],
    queryFn: () => fetchArtifacts(taskId),
    enabled: taskId.length > 0 && selectedTab === "artifacts",
    ...liveQueryOptions,
  });
  const contentQuery = useQuery({
    queryKey: ["artifact-content", taskId, selectedPath],
    queryFn: () => fetchArtifactContent(taskId, selectedPath ?? ""),
    enabled: taskId.length > 0 && Boolean(selectedPath),
    ...liveQueryOptions,
  });

  const actionMutation = useMutation({
    mutationFn: async (action: "analyze" | "run" | "report") => {
      if (action === "analyze") {
        return analyzeTask(taskId);
      }
      if (action === "run") {
        return runTask(taskId);
      }
      return reportTask(taskId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] });
      queryClient.invalidateQueries({ queryKey: ["task-artifacts", taskId] });
      queryClient.invalidateQueries({ queryKey: ["overview"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["task-report", taskId] });
    },
  });

  useEffect(() => {
    if (!detailQuery.data || detailQuery.data.attempts.length === 0) {
      return;
    }
    if (selectedAttemptNo === null) {
      setSelectedAttemptNo(detailQuery.data.attempts[detailQuery.data.attempts.length - 1].attempt_no);
    }
  }, [detailQuery.data, selectedAttemptNo, setSelectedAttemptNo]);

  const currentAttempt = useMemo(() => {
    if (!detailQuery.data || detailQuery.data.attempts.length === 0) {
      return null;
    }
    return (
      detailQuery.data.attempts.find((item) => item.attempt_no === selectedAttemptNo) ??
      detailQuery.data.attempts[detailQuery.data.attempts.length - 1]
    );
  }, [detailQuery.data, selectedAttemptNo]);

  const tabFiles = useMemo(
    () => buildTabFiles(detailQuery.data, selectedTab, currentAttempt, artifactsQuery.data?.items),
    [artifactsQuery.data?.items, currentAttempt, detailQuery.data, selectedTab],
  );
  const filePageCount = Math.max(1, Math.ceil(tabFiles.length / FILE_PAGE_SIZE));
  const visibleTabFiles = useMemo(() => {
    const start = (filePage - 1) * FILE_PAGE_SIZE;
    return tabFiles.slice(start, start + FILE_PAGE_SIZE);
  }, [filePage, tabFiles]);

  useEffect(() => {
    if (tabFiles.length === 0) {
      setSelectedPath(null);
      return;
    }
    if (!selectedPath || !tabFiles.includes(selectedPath)) {
      setSelectedPath(tabFiles[0]);
    }
  }, [selectedPath, tabFiles]);

  useEffect(() => {
    setFilePage(1);
  }, [selectedTab, currentAttempt?.attempt_no]);

  useEffect(() => {
    if (filePage > filePageCount) {
      setFilePage(filePageCount);
    }
  }, [filePage, filePageCount]);

  if (detailQuery.isLoading) {
    return <div className="pw-empty">正在加载任务详情...</div>;
  }

  if (detailQuery.isError || !detailQuery.data) {
    return <div className="pw-empty">当前无法获取任务详情，请确认任务存在且后端接口可用</div>;
  }

  const detail = detailQuery.data;

  return (
    <div className="pw-grid">
      <SectionCard
        title={detail.task.task_id}
        actions={
          <div className="pw-btn-row">
            <button
              className="pw-btn primary"
              type="button"
              onClick={() => actionMutation.mutate("run")}
              disabled={
                actionMutation.isPending ||
                ["running", "building", "validating", "reporting"].includes(detail.task.status) ||
                detail.task.current_attempt >= detail.task.max_attempts
              }
              title={
                detail.task.current_attempt >= detail.task.max_attempts
                  ? `已达最大尝试轮次 ${detail.task.max_attempts}`
                  : ["running", "building", "validating", "reporting"].includes(detail.task.status)
                  ? "任务正在执行中"
                  : "执行一轮构建验证"
              }
            >
              执行一轮
            </button>
            <button className="pw-btn" type="button" onClick={() => actionMutation.mutate("report")} disabled={actionMutation.isPending}>
              生成报告
            </button>
            <button className="pw-btn" type="button" onClick={() => void detailQuery.refetch()}>
              刷新
            </button>
          </div>
        }
      >
        <div className="pw-kv">
          <div className="pw-kv-item">
            <span className="pw-kv-label">CVE</span>
            <div className="pw-kv-value">{detail.task.cve_id}</div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">任务状态</span>
            <div className="pw-kv-value">
              <StatusBadge value={detail.task.status} />
            </div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">尝试轮次</span>
            <div className="pw-kv-value">
              {detail.task.current_attempt}/{detail.task.max_attempts}
            </div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">目标内核</span>
            <div className="pw-kv-value">{detail.task.target_kernel}</div>
          </div>
          {detail.task.latest_failure_type ? (
            <div className="pw-kv-item">
              <span className="pw-kv-label">失败类型</span>
              <div className="pw-kv-value">{detail.task.latest_failure_type}</div>
            </div>
          ) : null}
          <div className="pw-kv-item">
            <span className="pw-kv-label">创建时间</span>
            <div className="pw-kv-value">{formatTime(detail.task.created_at)}</div>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="阶段时间线" actions={<LiveEventBadge status={liveEventStatus} />}>
        <StageTimeline
          items={detail.stage_view ?? detail.timeline}
          currentStage={detail.process_summary?.current_stage}
          failureExplanation={detail.task.latest_failure_explanation ?? undefined}
          failureDiagnosis={detail.failure_diagnosis}
        />
      </SectionCard>

      <SectionCard title="智能体状态">
        <AgentPanel detail={detail} />
      </SectionCard>

      <SectionCard
        title="任务证据面板"
      >
        <div className="pw-tabs">
          {tabs.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`pw-tab${selectedTab === item.key ? " active" : ""}`}
              onClick={() => setSelectedTab(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="pw-grid detail">
          <div className="pw-grid">
            <SectionCard title="内容摘要">
              {renderTabSummary(detail, selectedTab, currentAttempt, setSelectedAttemptNo, setSelectedPath)}
            </SectionCard>
            <SectionCard title="候选文件">
              {tabFiles.length > 0 ? (
                <div className="pw-list">
                  <div className="pw-file-list-head">
                    <span>
                      共 {tabFiles.length} 个文件，第 {filePage}/{filePageCount} 页
                    </span>
                    <div className="pw-pagination-controls">
                      <button className="pw-btn compact" type="button" onClick={() => setFilePage(1)} disabled={filePage <= 1}>
                        首页
                      </button>
                      <button className="pw-btn compact" type="button" onClick={() => setFilePage((current) => Math.max(1, current - 1))} disabled={filePage <= 1}>
                        上一页
                      </button>
                      <button
                        className="pw-btn compact"
                        type="button"
                        onClick={() => setFilePage((current) => Math.min(filePageCount, current + 1))}
                        disabled={filePage >= filePageCount}
                      >
                        下一页
                      </button>
                    </div>
                  </div>
                  {visibleTabFiles.map((path) => (
                    <button
                      key={path}
                      type="button"
                      className={`pw-list-item pw-file-item${selectedPath === path ? " is-active" : ""}`}
                      onClick={() => setSelectedPath(path)}
                    >
                      <span className="pw-path-title">{path}</span>
                      <span className="pw-path-caption">选中后在右侧打开文件内容</span>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="pw-empty">当前标签下还没有匹配到可预览的产物文件</div>
              )}
            </SectionCard>
          </div>
          <CodePanel
            title="产物预览"
            path={selectedPath ?? undefined}
            content={
              contentQuery.isLoading
                ? "正在加载内容..."
                : contentQuery.isError
                  ? `无法打开文件\n${contentQuery.error instanceof Error ? contentQuery.error.message : "请确认文件仍存在"}`
                  : contentQuery.data?.content
            }
            emptyText="选择左侧候选文件后，这里会展示对应 artifact 的文本内容"
            actions={
              selectedPath ? (
                <div className="pw-btn-row">
                  <button className="pw-btn" type="button" onClick={() => void copyText(selectedPath)}>
                    复制路径
                  </button>
                </div>
              ) : null
            }
          />
        </div>
      </SectionCard>
    </div>
  );
}

function AgentDecisionTimeline({ detail }: { detail: TaskDetailResponse }): JSX.Element {
  const trace = detail.agent_trace;
  if (!trace?.present || trace.steps.length === 0) {
    return (
      <div className="pw-process-summary">
        <div className="pw-process-heading">
          <div>
            <strong>暂无智能体自动编排轨迹</strong>
            <div className="pw-inline-note">启用 PATCHWEAVER_AGENT_RUNTIME=langgraph 并通过 Web 自动运行后会生成轨迹</div>
          </div>
          <StatusBadge value="idle" />
        </div>
        <div className="pw-inline-note">目标：{detail.task.cve_id} / {detail.task.target_kernel}</div>
      </div>
    );
  }

  return (
    <div className="pw-process-summary">
      <div className="pw-process-heading">
        <div>
          <strong>目标 {trace.goal.cve_id}</strong>
          <div className="pw-inline-note">
            运行时 {trace.runtime ?? "未知"} / 检查点 {trace.checkpoint_exists ? "已写入" : "未写入"} / 恢复{" "}
            {trace.resumed_from_checkpoint ? "已恢复" : "未触发"}
          </div>
        </div>
        <StatusBadge value={trace.terminal_reason ? "terminal" : "running"} />
      </div>
      <div className="pw-agent-trace">
        {trace.steps.map((step) => (
          <div className="pw-agent-step" key={step.step_index}>
            <div className="pw-agent-step-head">
              <span className="pw-agent-step-index">步骤 {step.step_index}</span>
              <strong>{formatAgentAction(step.selected_action) ?? "未记录动作"}</strong>
              <StatusBadge value={step.guard_result === "allowed" ? "success" : step.guard_result ? "warn" : "unknown"} />
            </div>
            <div className="pw-process-grid">
              <div>
                <span className="pw-process-label">规划理由</span>
                <div>{step.reason_summary ?? "未记录"}</div>
              </div>
              <div>
                <span className="pw-process-label">安全检查</span>
                <div>{step.guard_result ?? "未记录"}</div>
              </div>
              <div>
                <span className="pw-process-label">工具结果</span>
                <div>{formatAgentAction(step.tool_action) ?? step.tool_result_status ?? "未执行"}</div>
              </div>
              <div>
                <span className="pw-process-label">检查点</span>
                <div>{step.checkpoint_status ?? "未记录"}</div>
              </div>
            </div>
            {step.alternatives?.length ? (
              <div className="pw-inline-note">候选策略：{step.alternatives.join(" / ")}</div>
            ) : null}
            {step.reflection_summary ? <div className="pw-process-conflict">反思记录：{step.reflection_summary}</div> : null}
            {step.next_strategy_hint ? <div className="pw-inline-note">下一策略：{step.next_strategy_hint}</div> : null}
            {step.terminal_reason ? <div className="pw-process-conflict">终止原因：{step.terminal_reason}</div> : null}
            {step.evidence_refs.length ? <div className="pw-inline-note">证据：{step.evidence_refs.join(" / ")}</div> : null}
          </div>
        ))}
      </div>
      <div className="pw-inline-note">轨迹文件：{shortenPath(trace.trace_path)}</div>
      <div className="pw-inline-note">检查点文件：{shortenPath(trace.checkpoint_path)}</div>
    </div>
  );
}

function LiveEventBadge({ status }: { status: string }): JSX.Element {
  const labels: Record<string, string> = {
    idle: "实时同步未启动",
    connecting: "实时同步连接中",
    connected: "实时同步已连接",
    reconnecting: "实时同步重连中",
    error: "实时同步异常",
  };
  return <span className={`pw-live-badge is-${status}`}>{labels[status] ?? "实时同步未知"}</span>;
}

function FailureDiagnosisPanel({ detail }: { detail: TaskDetailResponse }): JSX.Element | null {
  const diagnosis = detail.failure_diagnosis;
  if (!diagnosis?.present || detail.task.status === "built" || detail.task.status === "success" || detail.task.status === "reported") {
    return null;
  }

  return (
    <div className="pw-failure-diagnosis" role="status" aria-label="失败诊断">
      <div className="pw-failure-diagnosis-head">
        <div>
          <span className="pw-process-label">失败诊断</span>
          <strong>{diagnosis.reason}</strong>
        </div>
        <StatusBadge value="failed" />
      </div>
      <div className="pw-process-grid">
        <div>
          <span className="pw-process-label">失败阶段</span>
          <div>{diagnosis.stage_label}</div>
        </div>
        <div>
          <span className="pw-process-label">失败类型</span>
          <div>{diagnosis.failure_type}</div>
        </div>
        <div>
          <span className="pw-process-label">影响</span>
          <div>{diagnosis.impact}</div>
        </div>
        <div>
          <span className="pw-process-label">下一步</span>
          <div>{diagnosis.next_action}</div>
        </div>
      </div>
      <div className="pw-evidence-list">
        <span className="pw-process-label">证据</span>
        {diagnosis.evidence_paths.length > 0 ? (
          diagnosis.evidence_paths.map((path) => (
            <button
              className="pw-evidence-chip"
              key={path}
              type="button"
              onClick={() => void copyText(path)}
              title="点击复制证据路径"
            >
              {shortenPath(path)}
            </button>
          ))
        ) : (
          <span className="pw-inline-note">未记录证据路径</span>
        )}
      </div>
      {diagnosis.evidence_snippets?.length ? (
        <div className="pw-list compact">
          {diagnosis.evidence_snippets.map((snippet) => (
            <div className="pw-log-snippet" key={snippet}>
              {snippet}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function formatAgentAction(action?: string | null): string | null {
  if (!action) {
    return null;
  }
  const labels: Record<string, string> = {
    get_task_detail: "查询任务详情",
    analyze_source: "分析源码",
    analyze_task: "分析任务",
    run_attempt: "执行单轮构建验证",
    run_task: "执行构建验证",
    report: "生成报告",
    report_task: "生成任务报告",
    replay: "执行回放",
    replay_task: "执行任务回放",
    retry_with_strategy: "切换策略重试",
    repair_build_source_tree: "修复可写构建树",
    stop_manual_review: "停止自动执行并转人工复核",
  };
  return labels[action] ?? action;
}

function formatRecipe(recipe?: string | null): string | null {
  if (!recipe) return null;
  const labels: Record<string, string> = {
    semantic_guard_rewrite: "语义保护改写",
    smpl_primary: "SMPL 主路径改写",
    section_change_avoidance: "规避 section 变更",
    alternative_recipe: "备选改写路线",
    stable_source_baseline: "稳定源码基线对齐",
    reverse_unpatch: "反向撤销补丁",
    context_adapter: "上下文适配",
    dependency_target_inference: "依赖目标推断",
    expand_module_dependencies: "扩展模块依赖",
  };
  return labels[recipe] ?? recipe;
}

function AgentPanel({ detail }: { detail: TaskDetailResponse }): JSX.Element {
  const health = detail.agent_health ?? detail.task.agent_health;
  const summary = detail.agent_decision_summary;
  const latestDecision = summary?.workflow_trace?.latest_decision;
  const trace = detail.agent_trace;

  const problem = detail.task.latest_failure_explanation ?? detail.process_summary?.problem ?? detail.task.latest_failure_type;
  const nextAction = latestDecision?.selected_action ?? summary?.agent_next_action ?? detail.process_summary?.next_action;
  const strategy = summary?.strategy;
  const recipe = summary?.selected_recipe;
  const reason = latestDecision?.reason ?? summary?.failure_record?.summary;

  return (
    <div className="pw-process-summary">
      <div className="pw-process-heading">
        <div>
          <strong>{detail.process_summary?.headline ?? `目标 ${detail.task.cve_id}`}</strong>
          {detail.process_summary?.current_stage ? (
            <div className="pw-inline-note">当前阶段 {stageLabelMap[detail.process_summary.current_stage] ?? detail.process_summary.current_stage}</div>
          ) : null}
        </div>
        <StatusBadge value={health?.status ?? detail.process_summary?.overall_status ?? "unknown"} />
      </div>
      <div className="pw-process-grid">
        {problem ? (
          <div>
            <span className="pw-process-label">当前问题</span>
            <div>{problem}</div>
          </div>
        ) : null}
        {nextAction ? (
          <div>
            <span className="pw-process-label">下一步动作</span>
            <div>{formatAgentAction(nextAction) ?? nextAction}</div>
          </div>
        ) : null}
        {strategy && strategy !== recipe ? (
          <div>
            <span className="pw-process-label">最终策略</span>
            <div>{strategy}</div>
          </div>
        ) : null}
        {recipe ? (
          <div>
            <span className="pw-process-label">改写策略</span>
            <div>{formatRecipe(recipe) ?? recipe}</div>
          </div>
        ) : null}
      </div>
      {reason ? <div className="pw-process-conflict">决策理由：{reason}</div> : null}
      {health?.recommendations?.length ? (
        <div className="pw-process-conflict">建议动作：{health.recommendations.join("；")}</div>
      ) : null}
      {trace?.present && trace.steps.length > 0 ? (
        <div className="pw-agent-trace">
          {trace.steps.map((step) => (
            <div className="pw-agent-step" key={step.step_index}>
              <div className="pw-agent-step-head">
                <span className="pw-agent-step-index">步骤 {step.step_index}</span>
                <strong>{formatAgentAction(step.selected_action) ?? "未记录动作"}</strong>
                <StatusBadge value={step.terminal_reason ? "terminal" : step.guard_result === "allowed" ? "success" : step.guard_result ? "warn" : "unknown"} />
              </div>
              <div className="pw-process-grid">
                {step.reason_summary ? (
                  <div>
                    <span className="pw-process-label">规划理由</span>
                    <div>{step.reason_summary}</div>
                  </div>
                ) : null}
                {step.checkpoint_status ? (
                  <div>
                    <span className="pw-process-label">检查点</span>
                    <div>{step.checkpoint_status}</div>
                  </div>
                ) : null}
              </div>
              {step.alternatives?.length ? (
                <div className="pw-inline-note">候选策略：{step.alternatives.map((a) => formatAgentAction(a) ?? a).join(" / ")}</div>
              ) : null}
              {step.reflection_summary ? <div className="pw-process-conflict">反思记录：{step.reflection_summary}</div> : null}
              {step.terminal_reason ? <div className="pw-process-conflict">终止原因：{step.terminal_reason}</div> : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="pw-inline-note">暂无智能体决策轨迹</div>
      )}
    </div>
  );
}

function AgentWorkStatusPanel({ detail }: { detail: TaskDetailResponse }): JSX.Element {
  const health = detail.agent_health ?? detail.task.agent_health;
  const summary = detail.agent_decision_summary;
  const latestDecision = summary?.workflow_trace?.latest_decision;

  return (
    <div className="pw-process-summary">
      <div className="pw-process-heading">
        <div>
          <strong>智能体当前状态</strong>
          <div className="pw-inline-note">状态来自后端健康检查与工作流轨迹</div>
        </div>
        <StatusBadge value={health?.status ?? "unknown"} />
      </div>
      <div className="pw-process-grid">
        <div>
          <span className="pw-process-label">Observation</span>
          <div>{detail.process_summary?.problem ?? detail.task.latest_failure_type ?? "暂无关键问题"}</div>
        </div>
        <div>
          <span className="pw-process-label">Decision</span>
          <div>{latestDecision?.selected_action ?? summary?.agent_next_action ?? "未记录"}</div>
        </div>
        <div>
          <span className="pw-process-label">Action</span>
          <div>{latestDecision?.retry ? "继续重试并切换策略" : latestDecision?.terminal ? "停止自动执行" : "按当前主链推进"}</div>
        </div>
        <div>
          <span className="pw-process-label">Reduction</span>
          <div>{health?.status ?? detail.process_summary?.overall_status ?? "unknown"}</div>
        </div>
      </div>
      {health?.signals?.length ? (
        <div className="pw-inline-note">健康信号：{health.signals.join(" / ")}</div>
      ) : (
        <div className="pw-inline-note">健康信号：未记录</div>
      )}
      {health?.recommendations?.length ? (
        <div className="pw-process-conflict">建议动作：{health.recommendations.join("；")}</div>
      ) : null}
      {latestDecision?.reason ? <div className="pw-process-conflict">决策理由：{latestDecision.reason}</div> : null}
      {health?.source_paths?.agent_health ? (
        <div className="pw-inline-note">健康文件：{shortenPath(health.source_paths.agent_health)}</div>
      ) : null}
      {summary?.workflow_trace?.trace_path ? (
        <div className="pw-inline-note">轨迹文件：{shortenPath(summary.workflow_trace.trace_path)}</div>
      ) : null}
    </div>
  );
}

function AgentDecisionPanel({ detail }: { detail: TaskDetailResponse }): JSX.Element | null {
  const summary = detail.agent_decision_summary;
  if (!summary) {
    return null;
  }
  const repairIntentStrategy =
    typeof summary.repair_intent?.recommended_strategy === "string"
      ? summary.repair_intent.recommended_strategy
      : summary.strategy_switch.repair_intent_strategy;
  const latestDecision = summary.workflow_trace?.latest_decision;

  return (
    <div className="pw-process-summary">
      <div className="pw-process-grid">
        <div>
          <span className="pw-process-label">RepairIntent 策略</span>
          <div>{repairIntentStrategy ?? "未记录"}</div>
        </div>
        <div>
          <span className="pw-process-label">改写策略</span>
          <div>{formatRecipe(summary.selected_recipe) ?? summary.selected_recipe ?? "未记录"}</div>
        </div>
        <div>
          <span className="pw-process-label">最终策略</span>
          <div>{summary.strategy ?? "未记录"}</div>
        </div>
        <div>
          <span className="pw-process-label">失败类型</span>
          <div>{summary.failure_type ?? "无"}</div>
        </div>
        <div>
          <span className="pw-process-label">策略切换</span>
          <div>{summary.strategy_switch.switched ? "已切换" : "未切换"}</div>
        </div>
        <div>
          <span className="pw-process-label">下一步动作</span>
          <div>{summary.agent_next_action ?? "未记录"}</div>
        </div>
        <div>
          <span className="pw-process-label">智能体当前决策</span>
          <div>{formatAgentAction(latestDecision?.selected_action) ?? "未记录"}</div>
        </div>
        <div>
          <span className="pw-process-label">终止原因</span>
          <div>{summary.workflow_trace?.terminal_stop_reason ?? "未终止"}</div>
        </div>
      </div>
      <div className="pw-inline-note">RepairIntent: {shortenPath(summary.source_paths.repair_intent)}</div>
      <div className="pw-inline-note">FailureRecord: {shortenPath(summary.source_paths.failure_record)}</div>
      {summary.workflow_trace?.trace_path ? (
        <div className="pw-inline-note">轨迹文件：{shortenPath(summary.workflow_trace.trace_path)}</div>
      ) : null}
      {summary.failure_record.summary ? <div className="pw-process-conflict">归因摘要：{summary.failure_record.summary}</div> : null}
      {latestDecision?.reason ? <div className="pw-process-conflict">决策理由：{latestDecision.reason}</div> : null}
    </div>
  );
}

function ProcessSummaryPanel({ detail }: { detail: TaskDetailResponse }): JSX.Element | null {
  const summary = detail.process_summary;
  if (!summary) {
    return null;
  }

  return (
    <div className="pw-process-summary">
      <div className="pw-process-heading">
        <div>
          <strong>{summary.headline}</strong>
          <div className="pw-inline-note">
            当前阶段 {stageLabelMap[summary.current_stage] ?? summary.current_stage}，最近尝试轮 {summary.current_attempt_no ?? "未开始"}
          </div>
        </div>
        <StatusBadge value={summary.overall_status} />
      </div>
      <div className="pw-process-grid">
        <div>
          <span className="pw-process-label">已达效果</span>
          <div>{summary.reached_effect}</div>
        </div>
        <div>
          <span className="pw-process-label">缺失效果</span>
          <div>{summary.missing_effect}</div>
        </div>
        <div>
          <span className="pw-process-label">问题判断</span>
          <div>{summary.problem ?? "无关键失败类型"}</div>
        </div>
        <div>
          <span className="pw-process-label">下一步</span>
          <div>{summary.next_action}</div>
        </div>
      </div>
      <div className="pw-inline-note">证据：{summary.primary_evidence_path ?? "未记录"}</div>
      {summary.state_conflicts.length > 0 ? (
        <div className="pw-process-conflict">口径冲突：{summary.state_conflicts.join("；")}</div>
      ) : null}
    </div>
  );
}

function renderTabSummary(
  detail: TaskDetailResponse,
  tab: TabKey,
  currentAttempt: TaskAttempt | null,
  setSelectedAttemptNo: (value: number | null) => void,
  setSelectedPath: (value: string) => void,
): JSX.Element {
  if (tab === "overview") {
    return (
      <div className="pw-list">
        <div className="pw-list-item">
          <strong>最新失败记录</strong>
          <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 240 }}>
            {asPrettyJson(detail.latest_failure, "暂无 failure_record")}
          </pre>
        </div>
        <div className="pw-list-item">
          <strong>最新验证结果</strong>
          <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 240 }}>
            {asPrettyJson(detail.latest_validation, "暂无 validation_report")}
          </pre>
        </div>
      </div>
    );
  }

  if (tab === "input") {
    return (
      <div className="pw-list">
        <div className="pw-list-item">
          <strong>Patch Bundle 摘要</strong>
          <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 220 }}>
            {asPrettyJson(detail.patch_bundle, "暂无 patch_bundle 内容")}
          </pre>
        </div>
        <div className="pw-list-item">
          <strong>建议查看文件</strong>
          <div className="pw-inline-note">优先关注 `task_context.json`、`input/` 与 `normalized/` 下的归一化输入</div>
        </div>
      </div>
    );
  }

  if (tab === "analysis") {
    return (
      <div className="pw-list">
        <div className="pw-list-item">
          <strong>分析产物路径</strong>
          <div className="pw-inline-note">{shortenPath(detail.analysis.semantic_card_path)}</div>
          <div className="pw-inline-note">{shortenPath(detail.analysis.constraint_report_path)}</div>
          <div className="pw-inline-note">{shortenPath(detail.analysis.context_bundle_path)}</div>
          <div className="pw-inline-note">{shortenPath(detail.analysis.analysis_trace_path)}</div>
        </div>
        <div className="pw-list-item">
          <strong>最近一次改写计划</strong>
          <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 220 }}>
            {asPrettyJson(detail.latest_rewrite_plan, "暂无 rewrite_plan")}
          </pre>
        </div>
        <div className="pw-list-item">
          <strong>阶段评测摘要</strong>
          <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 240 }}>
            {asPrettyJson(detail.evaluation_summary, "暂无阶段评测摘要")}
          </pre>
        </div>
      </div>
    );
  }

  if (tab === "attempts") {
    return detail.attempts.length > 0 ? (
      <div className="pw-list">
        {detail.attempts.map((attempt) => (
          <button
            key={attempt.attempt_id}
            type="button"
            className="pw-list-item"
            style={{ textAlign: "left" }}
            onClick={() => {
              setSelectedAttemptNo(attempt.attempt_no);
              setSelectedPath(`attempts/${String(attempt.attempt_no).padStart(3, "0")}/rewrite/rewrite_plan.json`);
            }}
          >
            <strong>
              第 {attempt.attempt_no} 轮 · {attempt.attempt_id}
            </strong>
            <div className="pw-inline-note">
              状态 {attempt.status}，失败类型 {attempt.failure_type ?? "无"}
            </div>
            <div className="pw-inline-note">
              开始 {formatTime(attempt.started_at)}，结束 {formatTime(attempt.finished_at)}
            </div>
          </button>
        ))}
      </div>
    ) : (
      <div className="pw-empty">当前任务还没有任何尝试轮记录</div>
    );
  }

  if (tab === "build") {
    return (
      <div className="pw-list">
        <div className="pw-list-item">
          <strong>当前轮构建路径</strong>
          <div className="pw-inline-note">build log: {shortenPath(currentAttempt?.build_log_path)}</div>
          <div className="pw-inline-note">module: {shortenPath(currentAttempt?.module_path)}</div>
          <div className="pw-inline-note">rewritten patch: {shortenPath(currentAttempt?.rewritten_patch_path)}</div>
        </div>
        <div className="pw-list-item">
          <strong>失败记录路径</strong>
          <div className="pw-inline-note">{shortenPath(currentAttempt?.failure_record_path)}</div>
        </div>
      </div>
    );
  }

  if (tab === "validate") {
    return (
      <div className="pw-list">
        <div className="pw-list-item">
          <strong>最新验证结果</strong>
          <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 240 }}>
            {asPrettyJson(detail.latest_validation, "暂无 validation_report")}
          </pre>
        </div>
        <div className="pw-list-item">
          <strong>验证产物路径</strong>
          <div className="pw-inline-note">{shortenPath(currentAttempt?.validation_report_path)}</div>
        </div>
      </div>
    );
  }

  if (tab === "report") {
    return (
      <div className="pw-list">
        <div className="pw-list-item">
          <strong>报告路径</strong>
          <div className="pw-inline-note">JSON: {shortenPath(detail.reports.json_path)}</div>
          <div className="pw-inline-note">Markdown: {shortenPath(detail.reports.md_path)}</div>
        </div>
        <div className="pw-list-item">
          <strong>建议查看文件</strong>
          <div className="pw-inline-note">优先阅读 `reports/report.json`、`reports/report.md` 与 `reports/context/`</div>
        </div>
      </div>
    );
  }

  if (tab === "replay") {
    return (
      <div className="pw-list">
        <div className="pw-list-item">
          <strong>回放摘要</strong>
          <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 240 }}>
            {asPrettyJson(detail.replay, "暂无 replay 数据")}
          </pre>
        </div>
      </div>
    );
  }

  if (tab === "artifacts") {
    return (
      <div className="pw-list">
        <div className="pw-list-item">
          <strong>全量产物浏览</strong>
          <div className="pw-inline-note">这个标签会加载任务工作区下的完整 artifact 树，适合精细排障与答辩回放</div>
        </div>
      </div>
    );
  }

  return (
    <div className="pw-list">
      <div className="pw-list-item">
        <strong>当前轮状态</strong>
        <div className="pw-inline-note">
          {currentAttempt
            ? `第 ${currentAttempt.attempt_no} 轮 · ${currentAttempt.status} · ${currentAttempt.failure_type ?? "无失败类型"}`
            : "当前还没有可供查看的尝试轮"}
        </div>
      </div>
    </div>
  );
}

function buildTabFiles(
  detail: TaskDetailResponse | undefined,
  tab: TabKey,
  currentAttempt: TaskAttempt | null,
  artifactItems?: Array<{ relative_path: string; kind: "file" | "directory" }>,
): string[] {
  if (!detail) {
    return [];
  }

  const all = detail.artifact_index.map((item) => item.relative_path);
  const attemptPrefix = currentAttempt ? `attempts/${String(currentAttempt.attempt_no).padStart(3, "0")}/` : null;

  const predicateMap: Record<TabKey, (item: string) => boolean> = {
    overview: (item) => item.endsWith("reports/report.json") || item.endsWith("logs/failure_record.json"),
    input: (item) => item === "task_context.json" || item.startsWith("input/") || item.startsWith("normalized/"),
    analysis: (item) => item.startsWith("analysis/"),
    attempts: (item) => Boolean(attemptPrefix && item.startsWith(attemptPrefix)),
    build: (item) => Boolean(attemptPrefix && item.startsWith(attemptPrefix) && item.includes("/logs/")),
    validate: (item) =>
      Boolean(
        attemptPrefix &&
          item.startsWith(attemptPrefix) &&
          (item.includes("validation_report.json") || item.endsWith("validate.log")),
      ),
    report: (item) => item.startsWith("reports/"),
    replay: (item) =>
      Boolean(
        attemptPrefix &&
          item.startsWith(attemptPrefix) &&
          (item.endsWith("attempt_state.json") || item.includes("/trace/")),
      ),
    artifacts: () => false,
  };

  if (tab === "artifacts") {
    return uniquePaths((artifactItems ?? []).filter((item) => item.kind === "file").map((item) => item.relative_path));
  }

  return uniquePaths(all.filter(predicateMap[tab]));
}

function uniquePaths(paths: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const path of paths) {
    if (!path || seen.has(path)) {
      continue;
    }
    seen.add(path);
    result.push(path);
  }
  return result;
}

function asPrettyJson(value: unknown, emptyText: string): string {
  if (value === null || value === undefined) {
    return emptyText;
  }
  return JSON.stringify(value, null, 2);
}
