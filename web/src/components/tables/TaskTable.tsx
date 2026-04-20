import { useNavigate } from "react-router-dom";
import { StatusBadge } from "../status/StatusBadge";
import { formatTime } from "../../utils/format";
import type { TaskListItem } from "../../types/tasks";

type TaskTableProps = {
  items: TaskListItem[];
};

export function TaskTable({ items }: TaskTableProps): JSX.Element {
  const navigate = useNavigate();

  if (items.length === 0) {
    return <div className="pw-empty">当前没有可展示的任务记录。</div>;
  }

  return (
    <table className="pw-table pw-table-clickable">
      <thead>
        <tr>
          <th>任务</th>
          <th>CVE</th>
          <th>目标内核</th>
          <th>状态</th>
          <th>尝试轮</th>
          <th>最近失败</th>
          <th>更新时间</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.task_id} onClick={() => navigate(`/tasks/${item.task_id}`)}>
            <td>{item.task_id}</td>
            <td>{item.cve_id}</td>
            <td>{item.target_kernel}</td>
            <td>
              <StatusBadge value={item.status} />
            </td>
            <td>
              {item.current_attempt}/{item.max_attempts}
            </td>
            <td>{item.latest_failure_type ?? item.latest_failure_summary ?? "-"}</td>
            <td>{formatTime(item.updated_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
