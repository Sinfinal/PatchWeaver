import { useLocation } from "react-router-dom";
import { getApiBase } from "../../services/http";
import { projectSummary } from "../../content/projectContent";
import { useUiStore } from "../../store/uiStore";

const pageMeta = [
  {
    match: /^\/tasks\/new$/,
    title: "创建任务",
    subtitle: "按 CVE、目标内核和运行档位发起新的热补丁任务。",
  },
  {
    match: /^\/tasks\/[^/]+$/,
    title: "任务详情",
    subtitle: "查看某个任务从分析到回放的完整证据链与产物索引。",
  },
  {
    match: /^\/tasks/,
    title: "任务中心",
    subtitle: "聚焦任务列表、失败类型分布与快速过滤。",
  },
  {
    match: /^\/doctor/,
    title: "环境诊断",
    subtitle: "检查项目运行时、工作区、数据库和构建环境是否健康。",
  },
  {
    match: /^\/rules/,
    title: "规则与配方",
    subtitle: "查看 risk rules、primitive rules 与 recipe 目录结构。",
  },
  {
    match: /^\/skills/,
    title: "技能注册",
    subtitle: "查看 skill source priority、阶段入口与启用状态。",
  },
  {
    match: /^\/logs/,
    title: "日志尾流",
    subtitle: "围绕 system log 与 latest build log 做快速排障。",
  },
  {
    match: /^\/settings/,
    title: "配置快照",
    subtitle: "核对系统默认值、工作区路径与可交付配置。",
  },
  {
    match: /^\/overview/,
    title: "工程总览",
    subtitle: "保留任务、状态、故障与日志等最核心的运行视图。",
  },
];

export function AppHeader(): JSX.Element {
  const location = useLocation();
  const autoRefresh = useUiStore((state) => state.autoRefresh);
  const refreshIntervalSec = useUiStore((state) => state.refreshIntervalSec);
  const setAutoRefresh = useUiStore((state) => state.setAutoRefresh);
  const setRefreshIntervalSec = useUiStore((state) => state.setRefreshIntervalSec);
  const currentMeta = pageMeta.find((item) => item.match.test(location.pathname)) ?? pageMeta[pageMeta.length - 1];

  return (
    <div className="pw-topbar">
      <div className="pw-topbar-copy">
        <div className="pw-kicker">{projectSummary.alias}</div>
        <h2 className="pw-title">{currentMeta.title}</h2>
        <p className="pw-subtitle">{currentMeta.subtitle}</p>
      </div>
      <div className="pw-topbar-controls">
        <div className="pw-control-row">
          <div className="pw-control-pill">
            <strong>{getApiBase()}</strong>
          </div>
          <div className="pw-control-pill">
            <span className="pw-control-label">Kernel</span>
            <strong>6.6.102-5.2.an23.x86_64</strong>
          </div>
          <div className="pw-control-pill">
            <span className="pw-control-label">Refresh</span>
            <strong>{autoRefresh ? `${refreshIntervalSec}s` : "Off"}</strong>
          </div>
        </div>
        <div className="pw-control-row compact">
          <select
            className="pw-select pw-select-inline"
            aria-label="设置自动刷新间隔"
            value={refreshIntervalSec}
            onChange={(event) => setRefreshIntervalSec(Number(event.target.value))}
          >
            <option value={10}>10 秒</option>
            <option value={20}>20 秒</option>
            <option value={40}>40 秒</option>
            <option value={60}>60 秒</option>
          </select>
          <button className="pw-btn" onClick={() => setAutoRefresh(!autoRefresh)} type="button">
            {autoRefresh ? "暂停刷新" : "恢复刷新"}
          </button>
        </div>
      </div>
    </div>
  );
}
