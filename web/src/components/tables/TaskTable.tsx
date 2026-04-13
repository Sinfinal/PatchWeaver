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
    return <div className="pw-empty">当前没有任务记录。</div>;
  }

  return (
    <table className="pw-table">
      <thead>
        <tr>
          <th>Task</th>
          <th>CVE</th>
          <th>Kernel</th>
          <th>Status</th>
          <th>Attempt</th>
          <th>Failure</th>
          <th>Updated</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.task_id} onClick={() => navigate(`/tasks/${item.task_id}`)} style={{ cursor: "pointer" }}>
            <td>{item.task_id}</td>
            <td>{item.cve_id}</td>
            <td>{item.target_kernel}</td>
            <td>
              <StatusBadge value={item.status} />
            </td>
            <td>
              {item.current_attempt}/{item.max_attempts}
            </td>
            <td>{item.latest_failure_type ?? "-"}</td>
            <td>{formatTime(item.updated_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
