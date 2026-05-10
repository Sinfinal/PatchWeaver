import { Link, useLocation } from "react-router-dom";

const navGroups = [
  {
    title: "总览",
    items: [{ to: "/overview", label: "控制台总览" }],
  },
  {
    title: "任务",
    items: [
      { to: "/tasks", label: "任务中心" },
      { to: "/tasks/new", label: "创建任务" },
    ],
  },
  {
    title: "报告",
    items: [{ to: "/reports", label: "报告与评测" }],
  },
  {
    title: "工程",
    items: [
      { to: "/doctor", label: "环境诊断" },
      { to: "/rules", label: "规则与配方" },
      { to: "/skills", label: "技能与上下文" },
      { to: "/logs", label: "系统日志" },
    ],
  },
  {
    title: "配置",
    items: [{ to: "/settings", label: "配置快照" }],
  },
];

export function AppSidebar(): JSX.Element {
  const location = useLocation();
  const pathname = location.pathname.replace(/\/+$/, "") || "/";

  const isItemActive = (to: string): boolean => {
    if (to === "/overview") {
      return pathname === "/" || pathname === "/overview";
    }
    if (to === "/tasks") {
      return pathname === "/tasks" || /^\/tasks\/(?!new$)[^/]+$/.test(pathname);
    }
    if (to === "/tasks/new") {
      return pathname === "/tasks/new";
    }
    return pathname === to || pathname.startsWith(`${to}/`);
  };

  return (
    <aside className="pw-sidebar">
      <div className="pw-sidebar-orb" />
      <div className="pw-sidebar-brand">
        <h1 className="pw-sidebar-title">PatchWeaver</h1>
        <div className="pw-sidebar-line" />
      </div>
      {navGroups.map((group) => (
        <div key={group.title} className="pw-nav-section">
          <div className="pw-nav-section-title">{group.title}</div>
          <nav className="pw-nav">
            {group.items.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                aria-current={isItemActive(item.to) ? "page" : undefined}
                className={`pw-nav-link${isItemActive(item.to) ? " active" : ""}`}
              >
                <span className="pw-nav-link-title">{item.label}</span>
              </Link>
            ))}
          </nav>
        </div>
      ))}
    </aside>
  );
}
