import { useLocation } from "react-router-dom";
import { projectSummary } from "../../content/projectContent";

const pageMeta = [
  { match: /^\/tasks\/(?!new(?:\/|$))[^/]+$/, title: "任务详情" },
  { match: /^\/tasks/, title: "任务中心" },
  { match: /^\/reports\/tasks\/[^/]+$/, title: "任务报告" },
  { match: /^\/reports\/fixtures\/[^/]+\/[^/]+$/, title: "样例详情" },
  { match: /^\/reports\/fixtures\/[^/]+$/, title: "固定样例评测" },
  { match: /^\/reports/, title: "报告与评测" },
  { match: /^\/doctor/, title: "环境诊断" },
  { match: /^\/rules/, title: "规则与配方" },
  { match: /^\/skills/, title: "技能与上下文" },
  { match: /^\/logs/, title: "系统日志" },
  { match: /^\/settings/, title: "配置快照" },
  { match: /^\/overview/, title: "控制台总览" },
];

export function AppHeader(): JSX.Element {
  const location = useLocation();
  const currentMeta = pageMeta.find((item) => item.match.test(location.pathname)) ?? pageMeta[pageMeta.length - 1];

  return (
    <div className="pw-topbar">
      <div className="pw-topbar-copy">
        <div className="pw-kicker">{projectSummary.alias}</div>
        <h2 className="pw-title">{currentMeta.title}</h2>
      </div>
      <div className="pw-topbar-controls">
        <div className="pw-control-pill">
          <span className="pw-control-label">目标内核</span>
          <strong>6.6.102-5.2.an23.x86_64</strong>
        </div>
      </div>
    </div>
  );
}
