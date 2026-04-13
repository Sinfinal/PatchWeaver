import { StatusBadge } from "../status/StatusBadge";
import type { TimelineNode } from "../../types/tasks";

type StageTimelineProps = {
  items: TimelineNode[];
};

export function StageTimeline({ items }: StageTimelineProps): JSX.Element {
  if (items.length === 0) {
    return <div className="pw-empty">当前没有阶段记录。</div>;
  }

  return (
    <div className="pw-timeline">
      {items.map((item) => (
        <div key={item.stage} className="pw-timeline-node">
          <strong>{item.stage}</strong>
          <div style={{ marginTop: 10 }}>
            <StatusBadge value={item.status} />
          </div>
        </div>
      ))}
    </div>
  );
}
