import { StatusBadge } from "../status/StatusBadge";
import type { TimelineNode } from "../../types/tasks";

type StageTimelineProps = {
  items: TimelineNode[];
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

export function StageTimeline({ items }: StageTimelineProps): JSX.Element {
  if (items.length === 0) {
    return <div className="pw-empty">当前任务还没有生成阶段时间线。</div>;
  }

  return (
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
  );
}
