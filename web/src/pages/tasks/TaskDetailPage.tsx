import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { CodePanel } from "../../components/code/CodePanel";
import { SectionCard } from "../../components/layout/SectionCard";
import { StatusBadge } from "../../components/status/StatusBadge";
import { StageTimeline } from "../../components/timeline/StageTimeline";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
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

  useEffect(() => {
    if (tabFiles.length === 0) {
      setSelectedPath(null);
      return;
    }
    if (!selectedPath || !tabFiles.includes(selectedPath)) {
      setSelectedPath(tabFiles[0]);
    }
  }, [selectedPath, tabFiles]);

  if (detailQuery.isLoading) {
    return <div className="pw-empty">正在加载任务详情...</div>;
  }

  if (detailQuery.isError || !detailQuery.data) {
    return <div className="pw-empty">当前无法获取任务详情，请确认任务存在且后端接口可用。</div>;
  }

  const detail = detailQuery.data;

  return (
    <div className="pw-grid">
      <SectionCard
        title={detail.task.task_id}
        subtitle={`${detail.task.cve_id} · ${detail.task.target_kernel}`}
        actions={
          <div className="pw-btn-row">
            <button className="pw-btn" type="button" onClick={() => actionMutation.mutate("analyze")} disabled={actionMutation.isPending}>
              分析
            </button>
            <button
              className="pw-btn primary"
              type="button"
              onClick={() => actionMutation.mutate("run")}
              disabled={actionMutation.isPending}
            >
              执行一轮
            </button>
            <button className="pw-btn" type="button" onClick={() => actionMutation.mutate("report")} disabled={actionMutation.isPending}>
              生成报告
            </button>
            <button className="pw-btn" type="button" onClick={() => setSelectedTab("replay")}>
              查看回放
            </button>
            <button className="pw-btn" type="button" onClick={() => void detailQuery.refetch()}>
              刷新
            </button>
          </div>
        }
      >
        <div className="pw-kv">
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
            <span className="pw-kv-label">工作区</span>
            <div className="pw-kv-value">{shortenPath(detail.task.workspace_dir)}</div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">创建时间</span>
            <div className="pw-kv-value">{formatTime(detail.task.created_at)}</div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">最近更新时间</span>
            <div className="pw-kv-value">{formatTime(detail.task.updated_at)}</div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">工作区状态</span>
            <div className="pw-kv-value">{detail.workspace_exists ? "已生成" : "缺失"}</div>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="阶段时间线"
        subtitle="展示任务在主链路中的推进位置及各阶段产物状态。"
      >
        <StageTimeline items={detail.timeline} />
      </SectionCard>

      <SectionCard
        title="任务证据面板"
        subtitle="按阶段查看任务产物，并在右侧预览对应文件内容。"
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
            <SectionCard title="内容摘要" subtitle={getTabSubtitle(selectedTab)}>
              {renderTabSummary(detail, selectedTab, currentAttempt, setSelectedAttemptNo, setSelectedPath)}
            </SectionCard>
            <SectionCard title="候选文件" subtitle="列出当前标签下的可用文件，选中后在右侧加载内容。">
              {tabFiles.length > 0 ? (
                <div className="pw-list">
                  {tabFiles.map((path) => (
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
                <div className="pw-empty">当前标签下还没有匹配到可预览的产物文件。</div>
              )}
            </SectionCard>
          </div>
          <CodePanel
            title="产物预览"
            path={selectedPath ?? undefined}
            content={contentQuery.isLoading ? "正在加载内容..." : contentQuery.data?.content}
            emptyText="选择左侧候选文件后，这里会展示对应 artifact 的文本内容。"
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
            {asPrettyJson(detail.latest_failure, "暂无 failure_record。")}
          </pre>
        </div>
        <div className="pw-list-item">
          <strong>最新验证结果</strong>
          <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 240 }}>
            {asPrettyJson(detail.latest_validation, "暂无 validation_report。")}
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
            {asPrettyJson(detail.patch_bundle, "暂无 patch_bundle 内容。")}
          </pre>
        </div>
        <div className="pw-list-item">
          <strong>建议查看文件</strong>
          <div className="pw-inline-note">优先关注 `task_context.json`、`input/` 与 `normalized/` 下的归一化输入。</div>
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
            {asPrettyJson(detail.latest_rewrite_plan, "暂无 rewrite_plan。")}
          </pre>
        </div>
        <div className="pw-list-item">
          <strong>阶段评测摘要</strong>
          <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 240 }}>
            {asPrettyJson(detail.evaluation_summary, "暂无阶段评测摘要。")}
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
      <div className="pw-empty">当前任务还没有任何尝试轮记录。</div>
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
            {asPrettyJson(detail.latest_validation, "暂无 validation_report。")}
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
          <div className="pw-inline-note">优先阅读 `reports/report.json`、`reports/report.md` 与 `reports/context/`。</div>
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
            {asPrettyJson(detail.replay, "暂无 replay 数据。")}
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
          <div className="pw-inline-note">这个标签会加载任务工作区下的完整 artifact 树，适合精细排障与答辩回放。</div>
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
            : "当前还没有可供查看的尝试轮。"}
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
    return (artifactItems ?? []).filter((item) => item.kind === "file").map((item) => item.relative_path).filter(Boolean);
  }

  return all.filter(predicateMap[tab]);
}

function getTabSubtitle(tab: TabKey): string {
  const subtitles: Record<TabKey, string> = {
    overview: "查看任务状态、最近失败记录和最新验证结果。",
    input: "查看输入文件、Patch Bundle 和归一化产物。",
    analysis: "查看语义卡、约束报告、上下文包和分析轨迹。",
    attempts: "查看各轮尝试记录，并切换到对应改写产物。",
    build: "查看构建日志、失败记录和当前轮构建产物。",
    validate: "查看验证报告、验证日志和语义检查结果。",
    report: "查看任务报告、Markdown 输出和报告上下文文件。",
    replay: "查看最近一轮的 trace、attempt_state 和回放摘要。",
    artifacts: "浏览当前任务工作区内的全部产物文件。",
  };
  return subtitles[tab];
}

function asPrettyJson(value: unknown, emptyText: string): string {
  if (value === null || value === undefined) {
    return emptyText;
  }
  return JSON.stringify(value, null, 2);
}
