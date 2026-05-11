import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { projectSummary } from "../../content/projectContent";
import { useUiStore } from "../../store/uiStore";

const pageMeta = [
  {
    match: /^\/tasks\/(?!new(?:\/|$))[^/]+$/,
    title: "任务详情",
  },
  {
    match: /^\/tasks/,
    title: "任务中心",
  },
  {
    match: /^\/reports\/tasks\/[^/]+$/,
    title: "任务报告",
  },
  {
    match: /^\/reports\/fixtures\/[^/]+\/[^/]+$/,
    title: "样例详情",
  },
  {
    match: /^\/reports\/fixtures\/[^/]+$/,
    title: "固定样例评测",
  },
  {
    match: /^\/reports/,
    title: "报告与评测",
  },
  {
    match: /^\/doctor/,
    title: "环境诊断",
  },
  {
    match: /^\/rules/,
    title: "规则与配方",
  },
  {
    match: /^\/skills/,
    title: "技能与上下文",
  },
  {
    match: /^\/logs/,
    title: "系统日志",
  },
  {
    match: /^\/settings/,
    title: "配置快照",
  },
  {
    match: /^\/overview/,
    title: "控制台总览",
  },
];

const refreshIntervals = [10, 20, 40, 60];

export function AppHeader(): JSX.Element {
  const location = useLocation();
  const autoRefresh = useUiStore((state) => state.autoRefresh);
  const refreshIntervalSec = useUiStore((state) => state.refreshIntervalSec);
  const setAutoRefresh = useUiStore((state) => state.setAutoRefresh);
  const setRefreshIntervalSec = useUiStore((state) => state.setRefreshIntervalSec);
  const [menuOpen, setMenuOpen] = useState(false);
  const intervalMenuRef = useRef<HTMLDivElement | null>(null);
  const currentMeta = pageMeta.find((item) => item.match.test(location.pathname)) ?? pageMeta[pageMeta.length - 1];

  useEffect(() => {
    if (!menuOpen) {
      return undefined;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (intervalMenuRef.current && !intervalMenuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen]);

  return (
    <div className="pw-topbar">
      <div className="pw-topbar-copy">
        <div className="pw-kicker">{projectSummary.alias}</div>
        <h2 className="pw-title">{currentMeta.title}</h2>
      </div>
      <div className="pw-topbar-controls">
        <div className="pw-control-row">
          <div className="pw-control-pill">
            <span className="pw-control-label">默认内核</span>
            <strong>6.6.102-5.2.an23.x86_64</strong>
          </div>
          <div className="pw-control-pill">
            <span className="pw-control-label">自动刷新</span>
            <strong>{autoRefresh ? `每 ${refreshIntervalSec} 秒` : "已暂停"}</strong>
          </div>
        </div>
        <div className="pw-control-row compact">
          <div className="pw-interval-select" ref={intervalMenuRef}>
            <button
              className={`pw-interval-trigger${menuOpen ? " is-open" : ""}`}
              type="button"
              aria-haspopup="listbox"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((value) => !value)}
            >
              <span className="pw-interval-value">{refreshIntervalSec} 秒</span>
              <span className="pw-interval-chevron" aria-hidden="true" />
            </button>
            {menuOpen ? (
              <div className="pw-interval-menu" role="listbox" aria-label="设置自动刷新间隔">
                {refreshIntervals.map((value) => (
                  <button
                    key={value}
                    type="button"
                    role="option"
                    aria-selected={value === refreshIntervalSec}
                    className={`pw-interval-option${value === refreshIntervalSec ? " active" : ""}`}
                    onClick={() => {
                      setRefreshIntervalSec(value);
                      setMenuOpen(false);
                    }}
                  >
                    {value} 秒
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <button className="pw-btn" onClick={() => setAutoRefresh(!autoRefresh)} type="button">
            {autoRefresh ? "暂停刷新" : "恢复刷新"}
          </button>
        </div>
      </div>
    </div>
  );
}
