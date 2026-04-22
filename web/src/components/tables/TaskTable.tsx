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
          <th>构建执行态</th>
          <th>尝试轮</th>
          <th>样例分组</th>
          <th>最近失败</th>
          <th>更新时间</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.task_id} onClick={() => navigate(`/tasks/${item.task_id}`)}>
            <td>{item.task_id}</td>
            <td>{item.cve_id}</td>
            <td>
              <div>{item.target_kernel}</div>
              <div className="pw-inline-note">{item.target_kernel_source ? `来源 ${item.target_kernel_source}` : "来源未记录"}</div>
            </td>
            <td>
              <StatusBadge value={item.status} />
            </td>
            <td>
              <div>{item.latest_build_exec_status ?? "-"}</div>
              <div className="pw-inline-note">{item.latest_target_state ?? "未命中目标态"}</div>
            </td>
            <td>
              {item.current_attempt}/{item.max_attempts}
            </td>
            <td>
              <div>{item.fixture_group ?? "-"}</div>
              <div className="pw-inline-note">{item.fixture_id ?? "未绑定样例"}</div>
            </td>
            <td>{item.latest_failure_type ?? item.latest_failure_summary ?? "-"}</td>
            <td>{formatTime(item.updated_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
