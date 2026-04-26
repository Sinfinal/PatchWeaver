import { StatusBadge } from "../status/StatusBadge";
import type { TimelineNode } from "../../types/tasks";

type StageTimelineProps = {
  items: TimelineNode[];
  currentStage?: string | null;
};

type ProgressStage = {
  stage: string;
  label: string;
  fallbackDescription: string;
};

const stageLabelMap: Record<string, string> = {
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
  { stage: "prepare", label: "准备", fallbackDescription: "等待任务上下文和基础输入就绪。" },
  { stage: "analysis", label: "分析", fallbackDescription: "等待语义分析和约束理解完成。" },
  { stage: "diagnose", label: "诊断", fallbackDescription: "等待热补丁约束诊断结果。" },
  { stage: "plan", label: "规划", fallbackDescription: "等待改写路线和 recipe 选择。" },
  { stage: "rewrite", label: "改写", fallbackDescription: "等待 rewritten.patch 和改写留痕。" },
  { stage: "build", label: "构建", fallbackDescription: "等待构建预检查或真实构建结果。" },
  { stage: "classify", label: "归因", fallbackDescription: "等待失败归因或目标态分类结果。" },
  { stage: "validate", label: "验证", fallbackDescription: "等待验证报告和动态验证证据。" },
  { stage: "report", label: "报告", fallbackDescription: "等待结构化报告和回放摘要生成。" },
];

export function StageTimeline({ items, currentStage }: StageTimelineProps): JSX.Element {
  if (items.length === 0) {
    return <div className="pw-empty">当前任务还没有生成阶段时间线。</div>;
  }

  const progressItems = buildProgressItems(items);
  const currentIndex = resolveCurrentIndex(progressItems, currentStage);

  return (
    <div className="pw-timeline-stack">
      <div className="pw-step-progress" aria-label="任务阶段进度">
        {progressItems.map((item, index) => (
          <StepProgressItem
            key={item.stage}
            item={item}
            index={index}
            isCurrent={index === currentIndex}
            showConnector={index < progressItems.length - 1}
          />
        ))}
      </div>
      <div className="pw-timeline">
        {items.map((item) => (
          <div key={item.stage} className="pw-timeline-node">
            <div className="pw-stage-heading">
              <strong>{item.label ?? stageLabelMap[item.stage] ?? item.stage}</strong>
              <StatusBadge value={item.status} />
            </div>
            {item.current_effect ? <div className="pw-stage-text">{item.current_effect}</div> : null}
            {item.missing_effect ? <div className="pw-stage-muted">缺口：{item.missing_effect}</div> : null}
            {item.problem ? <div className="pw-stage-muted">问题：{item.problem}</div> : null}
            {item.analysis ? <div className="pw-stage-muted">判断：{item.analysis}</div> : null}
            {item.next_action ? <div className="pw-stage-muted">下一步：{item.next_action}</div> : null}
            {item.primary_evidence_path ?? item.path ? (
              <div className="pw-inline-note">证据：{item.primary_evidence_path ?? item.path}</div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function buildProgressItems(items: TimelineNode[]): TimelineNode[] {
  const stageMap = new Map(items.map((item) => [item.stage, item]));

  return progressStages.map((progressStage) => {
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
}

function StepProgressItem({
  item,
  index,
  isCurrent,
  showConnector,
}: {
  item: TimelineNode;
  index: number;
  isCurrent: boolean;
  showConnector: boolean;
}): JSX.Element {
  const normalizedStatus = normalizeProgressStatus(item.status);
  const connectorClass = `pw-step-connector is-${normalizedStatus}`;
  const itemClass = `pw-step-item is-${normalizedStatus}${isCurrent ? " is-current" : ""}`;
  const label = item.label ?? stageLabelMap[item.stage] ?? item.stage;
  const description = buildStepDescription(item);

  return (
    <>
      <div className={itemClass} aria-current={isCurrent ? "step" : undefined}>
        <div className="pw-step-head">
          <span className="pw-step-marker">{stepMarker(normalizedStatus, index)}</span>
          <span className="pw-step-title">{label}</span>
        </div>
        <div className="pw-step-description">{description}</div>
      </div>
      {showConnector ? <div className={connectorClass} aria-hidden="true" /> : null}
    </>
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
    failure_analysis: "classify",
    replay: "report",
  };

  return stageAliasMap[currentStage] ?? currentStage;
}

function isSettledStatus(status?: string | null): boolean {
  return ["success", "skipped"].includes(normalizeProgressStatus(status));
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
  return "pending";
}

function stepMarker(status: string, index: number): string {
  if (status === "success") {
    return "✓";
  }
  if (status === "failed") {
    return "×";
  }
  return "";
}

function buildStepDescription(item: TimelineNode): string {
  return item.current_effect ?? item.problem ?? item.missing_effect ?? item.analysis ?? "等待该阶段推进。";
}

function resolveProgressSource(stage: string, stageMap: Map<string, TimelineNode>): TimelineNode | undefined {
  const stageAliases: Record<string, string[]> = {
    prepare: ["prepare"],
    analysis: ["analysis", "semantic_card"],
    diagnose: ["diagnose", "constraint_diagnosis"],
    plan: ["plan"],
    rewrite: ["rewrite", "rewrite_recipe"],
    build: ["build"],
    classify: ["classify", "failure_analysis"],
    validate: ["validate"],
    report: ["report", "replay"],
  };

  return (stageAliases[stage] ?? [stage]).map((alias) => stageMap.get(alias)).find((item) => item !== undefined);
}
