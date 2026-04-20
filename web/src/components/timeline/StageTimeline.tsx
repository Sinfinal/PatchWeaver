import { StatusBadge } from "../status/StatusBadge";
import type { TimelineNode } from "../../types/tasks";

type StageTimelineProps = {
  items: TimelineNode[];
};

const stageLabelMap: Record<string, string> = {
  prepare: "准备",
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
  validate: "验证",
  report: "报告",
  replay: "回放",
};

export function StageTimeline({ items }: StageTimelineProps): JSX.Element {
  if (items.length === 0) {
    return <div className="pw-empty">当前任务还没有生成阶段时间线。</div>;
  }

  return (
    <div className="pw-timeline">
      {items.map((item) => (
        <div key={item.stage} className="pw-timeline-node">
          <strong>{stageLabelMap[item.stage] ?? item.stage}</strong>
          {item.path ? <div className="pw-inline-note">{item.path}</div> : null}
          <div style={{ marginTop: 10 }}>
            <StatusBadge value={item.status} />
          </div>
        </div>
      ))}
    </div>
  );
}
