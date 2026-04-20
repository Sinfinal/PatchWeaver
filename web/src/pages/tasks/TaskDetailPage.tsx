import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { CodePanel } from "../../components/code/CodePanel";
import { SectionCard } from "../../components/layout/SectionCard";
import { StatusBadge } from "../../components/status/StatusBadge";
import { StageTimeline } from "../../components/timeline/StageTimeline";
import { analyzeTask, fetchArtifactContent, fetchArtifacts, fetchTaskDetail, reportTask, runTask } from "../../services/tasks";
import { useUiStore } from "../../store/uiStore";
import { copyText, formatTime } from "../../utils/format";
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
  const selectedAttemptNo = useUiStore((state) => state.selectedAttemptNo);
  const setSelectedAttemptNo = useUiStore((state) => state.setSelectedAttemptNo);
  const [selectedTab, setSelectedTab] = useState<TabKey>("overview");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  const detailQuery = useQuery({
    queryKey: ["task-detail", taskId],
    queryFn: () => fetchTaskDetail(taskId),
    enabled: taskId.length > 0,
  });
  const artifactsQuery = useQuery({
    queryKey: ["task-artifacts", taskId],
    queryFn: () => fetchArtifacts(taskId),
    enabled: taskId.length > 0 && selectedTab === "artifacts",
  });
  const contentQuery = useQuery({
    queryKey: ["artifact-content", taskId, selectedPath],
    queryFn: () => fetchArtifactContent(taskId, selectedPath ?? ""),
    enabled: taskId.length > 0 && Boolean(selectedPath),
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

  const tabFiles = useMemo(() => buildTabFiles(detailQuery.data, selectedTab, currentAttempt, artifactsQuery.data?.items), [
    artifactsQuery.data?.items,
    currentAttempt,
    detailQuery.data,
    selectedTab,
  ]);

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
    return <div className="pw-empty">任务详情加载中...</div>;
  }

  if (detailQuery.isError || !detailQuery.data) {
    return <div className="pw-empty">任务详情加载失败。</div>;
  }

  const detail = detailQuery.data;

  return (
    <div className="pw-grid">
      <SectionCard
        title={detail.task.task_id}
        subtitle={`${detail.task.cve_id} · ${detail.task.target_kernel}`}
        actions={
          <div className="pw-btn-row">
            <button className="pw-btn" type="button" onClick={() => actionMutation.mutate("analyze")}>
              分析
            </button>
            <button className="pw-btn primary" type="button" onClick={() => actionMutation.mutate("run")}>
              执行一轮
            </button>
            <button className="pw-btn" type="button" onClick={() => actionMutation.mutate("report")}>
              生成报告
            </button>
          </div>
        }
      >
        <div className="pw-kv">
          <div className="pw-kv-item">
            <span className="pw-kv-label">状态</span>
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
            <div className="pw-kv-value">{detail.task.workspace_dir}</div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">更新时间</span>
            <div className="pw-kv-value">{formatTime(detail.task.updated_at)}</div>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="阶段时间线" subtitle="按产物落盘情况给出当前任务阶段快照">
        <StageTimeline items={detail.timeline} />
      </SectionCard>

      <SectionCard title="页面标签" subtitle="同一任务下切换输入、分析、构建和报告视图">
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
            <SectionCard title="当前标签内容" subtitle={getTabSubtitle(selectedTab)}>
              {renderTabSummary(detail, selectedTab, currentAttempt, setSelectedAttemptNo, setSelectedPath)}
            </SectionCard>
            <SectionCard title="可查看文件" subtitle="点击后在右侧代码面板预览">
              {tabFiles.length > 0 ? (
                <div className="pw-list">
                  {tabFiles.map((path) => (
                    <button
                      key={path}
                      type="button"
                      className="pw-list-item"
                      style={{ textAlign: "left" }}
                      onClick={() => setSelectedPath(path)}
                    >
                      <strong>{path}</strong>
                      <span className="pw-inline-note">点击后在右侧打开</span>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="pw-empty">这个标签下暂时没有文件可展示。</div>
              )}
            </SectionCard>
          </div>
          <CodePanel
            title="产物预览"
            path={selectedPath ?? undefined}
            content={contentQuery.data?.content}
            emptyText="选择一个产物文件后，这里会展示其内容。"
            actions={
              selectedPath ? (
                <div className="pw-btn-row">
                  <button className="pw-btn" type="button" onClick={() => copyText(selectedPath)}>
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
          <strong>最近失败摘要</strong>
          <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 240 }}>
            {JSON.stringify(detail.latest_failure ?? {}, null, 2) || "暂无失败记录"}
          </pre>
        </div>
        <div className="pw-list-item">
          <strong>最近验证结果</strong>
          <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 240 }}>
            {JSON.stringify(detail.latest_validation ?? {}, null, 2) || "暂无验证记录"}
          </pre>
        </div>
        <div className="pw-list-item">
          <strong>阶段评测摘要</strong>
          <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 240 }}>
            {JSON.stringify(detail.evaluation_summary ?? {}, null, 2) || "暂无阶段评测摘要"}
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
              状态: {attempt.status} · 失败类型: {attempt.failure_type ?? "无"}
            </div>
          </button>
        ))}
      </div>
    ) : (
      <div className="pw-empty">当前还没有尝试轮记录。</div>
    );
  }

  if (tab === "replay") {
    return (
      <div className="pw-list">
        <div className="pw-list-item">
          <strong>最近回放</strong>
          <pre className="pw-code-content" style={{ padding: 0, marginTop: 10, maxHeight: 240 }}>
            {JSON.stringify(detail.replay, null, 2)}
          </pre>
        </div>
      </div>
    );
  }

  return (
    <div className="pw-list">
      <div className="pw-list-item">
        <strong>当前尝试</strong>
        <div className="pw-inline-note">
          {currentAttempt
            ? `第 ${currentAttempt.attempt_no} 轮 · ${currentAttempt.status} · ${currentAttempt.failure_type ?? "无失败类型"}`
            : "当前还没有尝试轮"}
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
    overview: "展示当前任务的状态、最新失败和验证结果。",
    input: "查看任务输入、原始 patch 和规范化 patch。",
    analysis: "查看 semantic card、constraint report 和分析轨迹。",
    attempts: "查看每轮尝试和对应的改写结果。",
    build: "查看 build.log、failure_record 和构建阶段输出。",
    validate: "查看 validation_report 和 validate.log。",
    report: "查看 report.json、report.md 及相关上下文。",
    replay: "查看最近一轮的 trace、attempt_state 和回放文件。",
    artifacts: "浏览整个工作区的产物树。",
  };
  return subtitles[tab];
}
