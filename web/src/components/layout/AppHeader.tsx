import { useLocation } from "react-router-dom";
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
    subtitle: "查看任务从输入、分析、改写到构建、验证和回放的完整证据链。",
  },
  {
    match: /^\/tasks/,
    title: "任务中心",
    subtitle: "围绕状态、失败类型和目标内核快速筛选任务，并直接进入详情排障。",
  },
  {
    match: /^\/reports\/tasks\/[^/]+$/,
    title: "任务报告",
    subtitle: "集中查看任务级报告、回放摘要和关键交付产物。",
  },
  {
    match: /^\/reports\/fixtures\/[^/]+\/[^/]+$/,
    title: "样例详情",
    subtitle: "查看单个固定样例的任务摘要、失败归因和回放对比结果。",
  },
  {
    match: /^\/reports\/fixtures\/[^/]+$/,
    title: "固定样例评测",
    subtitle: "按评测分组查看 summary.json、summary.md 和单样例结果清单。",
  },
  {
    match: /^\/reports/,
    title: "报告与评测",
    subtitle: "围绕任务报告、固定样例与阶段统计构建统一的展示与复盘入口。",
  },
  {
    match: /^\/doctor/,
    title: "环境诊断",
    subtitle: "检查项目运行时、工作区、数据库和构建环境是否健康。",
  },
  {
    match: /^\/rules/,
    title: "规则与配方",
    subtitle: "查看风险规则、原语规则与 Recipe 的目录现状。",
  },
  {
    match: /^\/skills/,
    title: "技能与上下文",
    subtitle: "查看 Skill Registry、来源优先级和阶段路由入口。",
  },
  {
    match: /^\/logs/,
    title: "系统日志",
    subtitle: "围绕 system log 与 latest build log 做快速排障。",
  },
  {
    match: /^\/settings/,
    title: "配置快照",
    subtitle: "核对系统默认值、工作区路径与交付配置。",
  },
  {
    match: /^\/overview/,
    title: "控制台总览",
    subtitle: "把任务、异常、评测与日志浓缩到一屏可读的工程视图。",
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
            <span className="pw-control-label">默认内核</span>
            <strong>6.6.102-5.2.an23.x86_64</strong>
          </div>
          <div className="pw-control-pill">
            <span className="pw-control-label">自动刷新</span>
            <strong>{autoRefresh ? `每 ${refreshIntervalSec}s` : "已暂停"}</strong>
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
