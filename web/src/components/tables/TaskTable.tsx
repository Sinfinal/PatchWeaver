import { useNavigate } from "react-router-dom";
import { StatusBadge } from "../status/StatusBadge";
import { formatTime } from "../../utils/format";
import type { TaskListItem } from "../../types/tasks";

function getSummary(item: TaskListItem): string {
  const s = item.status;
  if (s === "built" || s === "reported") return "构建成功";
  if (s === "created") return "等待启动";
  if (s === "analyzed") return "分析完成，等待构建";
  if (s === "running" || s === "building" || s === "validating") return "进行中...";
  if (item.latest_failure_explanation) return item.latest_failure_explanation;
  if (item.latest_failure_type) return item.latest_failure_type;
  return "-";
}

type TaskTableProps = {
  items: TaskListItem[];
};

const STATUS_ROWS = [
  { label: "已创建", desc: "任务已提交，等待 Agent 启动", color: "#8b9ab0" },
  { label: "已分析", desc: "CVE 和补丁分析完成", color: "#a78bfa" },
  { label: "运行中", desc: "Agent 正在执行构建验证", color: "#61b8ff" },
  { label: "构建中", desc: "kpatch-build 正在构建热补丁", color: "#38bdf8" },
  { label: "验证中", desc: "正在执行加载/卸载/回归验证", color: "#22d3ee" },
  { label: "已构建", desc: "热补丁 .ko 构建成功", color: "#34d399" },
  { label: "已报告", desc: "完成报告和回放证据", color: "#52d273" },
  { label: "失败", desc: "当前轮次失败，可能继续重试", color: "#ff6b6b" },
];

function StatusTooltip(): JSX.Element {
  return (
    <span className="pw-status-help">
      <span className="pw-status-help-icon">?</span>
      <div className="pw-status-help-popup">
        <div className="pw-status-help-title">状态说明</div>
        {STATUS_ROWS.map((row) => (
          <div key={row.label} className="pw-status-help-row">
            <span className="pw-status-help-dot" style={{ background: row.color }} />
            <span className="pw-status-help-name">{row.label}</span>
            <span className="pw-status-help-desc">{row.desc}</span>
          </div>
        ))}
      </div>
    </span>
  );
}

export function TaskTable({ items }: TaskTableProps): JSX.Element {
  const navigate = useNavigate();

  if (items.length === 0) {
    return <div className="pw-empty">当前没有可展示的任务记录</div>;
  }

  return (
    <table className="pw-table pw-table-clickable">
      <thead>
        <tr>
          <th>任务</th>
          <th>CVE</th>
          <th>目标内核</th>
          <th>状态 <StatusTooltip /></th>
          <th>尝试轮</th>
          <th>摘要</th>
          <th>更新时间</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.task_id} onClick={() => navigate(`/tasks/${item.task_id}`)}>
            <td>{item.task_id}</td>
            <td>{item.cve_id}</td>
            <td>{item.target_kernel}</td>
            <td><StatusBadge value={item.status} /></td>
            <td>{item.current_attempt}/{item.max_attempts}</td>
            <td>{getSummary(item)}</td>
            <td>{formatTime(item.updated_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

