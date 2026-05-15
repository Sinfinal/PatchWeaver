import { StatusBadge } from "../status/StatusBadge";
import type { FailureDiagnosis, TimelineNode } from "../../types/tasks";

type StageTimelineProps = {
  items: TimelineNode[];
  currentStage?: string | null;
  failureExplanation?: string;
  failureDiagnosis?: FailureDiagnosis | null;
};

type ProgressStage = {
  stage: string;
  label: string;
  fallbackDescription: string;
};

export const stageLabelMap: Record<string, string> = {
  prepare: "准备",
  source: "来源获取",
  retrieve: "检索",
  input: "输入整理",
  analysis: "分析",
  semantic_card: "语义卡片",
  diagnose: "诊断",
  constraint_diagnosis: "约束诊断",
  plan: "规划",
  rewrite: "改写",
  rewrite_recipe: "Recipe 改写",
  build: "构建",
  classify: "归因",
  failure_analysis: "失败归因",
  validate: "验证",
  report: "报告",
  replay: "回放",
};

const progressStages: ProgressStage[] = [
  { stage: "prepare", label: "准备", fallbackDescription: "等待任务上下文和基础输入就绪" },
  { stage: "source", label: "来源获取", fallbackDescription: "等待 CVE 来源链和补丁来源就绪" },
  { stage: "analysis", label: "语义分析", fallbackDescription: "等待语义分析和约束理解完成" },
  { stage: "diagnose", label: "约束诊断", fallbackDescription: "等待热补丁约束诊断结果" },
  { stage: "plan", label: "改写规划", fallbackDescription: "等待改写路线和 recipe 选择" },
  { stage: "rewrite", label: "补丁改写", fallbackDescription: "等待 rewritten.patch 和改写留痕" },
  { stage: "build", label: "构建预检", fallbackDescription: "等待构建预检查或真实构建结果" },
  { stage: "validate", label: "动态验证", fallbackDescription: "等待验证报告和动态验证证据" },
  { stage: "report", label: "报告与回放", fallbackDescription: "等待结构化报告和回放摘要生成" },
];

export function StageTimeline({ items, currentStage, failureExplanation, failureDiagnosis }: StageTimelineProps): JSX.Element {
  if (items.length === 0) {
    return <div className="pw-empty">当前任务还没有生成阶段时间线</div>;
  }

  const progressItems = buildProgressItems(items);
  const currentIndex = resolveCurrentIndex(progressItems, currentStage);

  return (
    <div className="pw-timeline-stack">
      <div className="pw-timeline" aria-label="任务阶段时间线">
        {progressItems.map((item, index) => (
          <StageTimelineNode
            key={item.stage}
            item={item}
            index={index}
            isCurrent={index === currentIndex}
            failureExplanation={failureExplanation}
            failureDiagnosis={failureDiagnosis}
          />
        ))}
      </div>
    </div>
  );
}

function buildProgressItems(items: TimelineNode[]): TimelineNode[] {
  const stageMap = new Map(items.map((item) => [item.stage, item]));

  const progressItems = progressStages.map((progressStage) => {
    const matchedItem = resolveProgressSource(progressStage.stage, stageMap);
    if (!matchedItem) {
      return {
        stage: progressStage.stage,
        label: progressStage.label,
        status: "pending",
        current_effect: progressStage.fallbackDescription,
      };
    }

    return {
      ...matchedItem,
      stage: progressStage.stage,
      label: progressStage.label,
    };
  });

  return linearizeProgressItems(progressItems);
}

function StageTimelineNode({
  item,
  index,
  isCurrent,
  failureExplanation,
  failureDiagnosis,
}: {
  item: TimelineNode;
  index: number;
  isCurrent: boolean;
  failureExplanation?: string;
  failureDiagnosis?: FailureDiagnosis | null;
}): JSX.Element {
  const normalizedStatus = normalizeProgressStatus(item.status);
  const itemClass = `pw-timeline-node is-${normalizedStatus}${isCurrent ? " is-current" : ""}`;
  const label = item.label ?? stageLabelMap[item.stage] ?? item.stage;
  const isFailed = normalizedStatus === "failed";
  const showDiagnosis = isFailed && failureDiagnosis?.present;

  return (
    <div className={itemClass} aria-current={isCurrent ? "step" : undefined}>
      <span className="pw-timeline-marker">{String(index + 1).padStart(2, "0")}</span>
      <div className="pw-stage-heading">
        <strong>{label}</strong>
        <StatusBadge value={item.status} />
      </div>
      {normalizedStatus !== "blocked" && normalizedStatus !== "pending" ? (
        <>
          {item.current_effect ? <div className="pw-stage-text">{item.current_effect}</div> : null}
          {item.missing_effect && item.missing_effect !== "无" ? <div className="pw-stage-muted">缺口：{item.missing_effect}</div> : null}
          {isFailed && failureExplanation ? (
            <div className="pw-stage-muted">问题：{failureExplanation}</div>
          ) : item.problem ? (
            <div className="pw-stage-muted">问题：{item.problem}</div>
          ) : null}
          {item.next_action ? <div className="pw-stage-muted">下一步：{item.next_action}</div> : null}
          {showDiagnosis ? (
            <div className="pw-failure-diagnosis" role="status" aria-label="失败诊断">
              <div className="pw-failure-diagnosis-head">
                <div>
                  <span className="pw-process-label">失败诊断</span>
                  <strong>{failureDiagnosis.reason}</strong>
                </div>
                <StatusBadge value="failed" />
              </div>
              <div className="pw-process-grid">
                <div>
                  <span className="pw-process-label">影响</span>
                  <div>{failureDiagnosis.impact}</div>
                </div>
                <div>
                  <span className="pw-process-label">下一步</span>
                  <div>{failureDiagnosis.next_action}</div>
                </div>
              </div>
              {failureDiagnosis.evidence_snippets?.length ? (
                <div className="pw-list compact">
                  {failureDiagnosis.evidence_snippets.map((snippet) => (
                    <div className="pw-log-snippet" key={snippet}>{snippet}</div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function resolveCurrentIndex(items: TimelineNode[], currentStage?: string | null): number {
  const normalizedStage = normalizeCurrentStage(currentStage);
  if (normalizedStage) {
    const stageIndex = items.findIndex((item) => item.stage === normalizedStage);
    if (stageIndex >= 0) {
      return stageIndex;
    }
  }

  const failedIndex = items.findIndex((item) => normalizeProgressStatus(item.status) === "failed");
  if (failedIndex >= 0) {
    return failedIndex;
  }

  const currentIndex = items.findIndex((item) => !isSettledStatus(item.status));
  return currentIndex >= 0 ? currentIndex : Math.max(items.length - 1, 0);
}

function normalizeCurrentStage(currentStage?: string | null): string | null {
  if (!currentStage) {
    return null;
  }

  const stageAliasMap: Record<string, string> = {
    source: "prepare",
    retrieve: "prepare",
    input: "prepare",
    semantic_card: "analysis",
    constraint_diagnosis: "diagnose",
    rewrite_recipe: "rewrite",
    build_precheck: "build",
    failure_analysis: "build",
    replay: "report",
  };

  return stageAliasMap[currentStage] ?? currentStage;
}

function isSettledStatus(status?: string | null): boolean {
  return ["success", "skipped", "blocked"].includes(normalizeProgressStatus(status));
}

function normalizeProgressStatus(status?: string | null): string {
  const normalized = (status ?? "").toLowerCase();
  if (["ok", "built", "success", "succeeded", "reported", "completed", "passed", "ready", "healthy", "matched"].includes(normalized)) {
    return "success";
  }
  if (["failed", "error", "danger", "missing", "unsupported", "unreachable", "unmatched"].includes(normalized)) {
    return "failed";
  }
  if (["created", "analyzed", "running", "building", "validating", "reporting", "processing", "loading"].includes(normalized)) {
    return "running";
  }
  if (["skipped"].includes(normalized)) {
    return "skipped";
  }
  if (["blocked"].includes(normalized)) {
    return "blocked";
  }
  return "pending";
}

function resolveProgressSource(stage: string, stageMap: Map<string, TimelineNode>): TimelineNode | undefined {
  const stageAliases: Record<string, string[]> = {
    prepare: ["prepare"],
    source: ["source", "retrieve", "input"],
    analysis: ["analysis", "semantic_card"],
    diagnose: ["diagnose", "constraint_diagnosis"],
    plan: ["plan"],
    rewrite: ["rewrite", "rewrite_recipe"],
    build: ["build"],
    validate: ["validate"],
    report: ["report", "replay"],
  };

  return (stageAliases[stage] ?? [stage]).map((alias) => stageMap.get(alias)).find((item) => item !== undefined);
}

function linearizeProgressItems(items: TimelineNode[]): TimelineNode[] {
  const failureIndex = items.findIndex((item) => normalizeProgressStatus(item.status) === "failed");
  if (failureIndex < 0) {
    return items;
  }

  const failedItem = items[failureIndex];
  const failedLabel = failedItem.label ?? stageLabelMap[failedItem.stage] ?? failedItem.stage;
  const failedProblem = failedItem.problem ?? "blocked_by_previous_failure";
  const failedNextAction = failedItem.next_action ?? "先处理前置失败";

  return items.map((item, index) => {
    if (index <= failureIndex) {
      return item;
    }
    return {
      ...item,
      status: "blocked",
      current_effect: `主链已在${failedLabel}失败，本阶段未进入成功链路`,
      missing_effect: "前置失败未解决，不能判定本阶段成功",
      problem: item.problem ?? failedProblem,
      analysis: "线性时间轴按首个失败阶段截断，后处理产物不计为阶段成功",
      next_action: failedNextAction,
    };
  });
}
