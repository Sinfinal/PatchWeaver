import { NavLink, useLocation } from "react-router-dom";

const navGroups = [
  {
    title: "Overview",
    items: [{ to: "/overview", label: "工程总览" }],
  },
  {
    title: "Tasks",
    items: [
      { to: "/tasks", label: "任务中心" },
      { to: "/tasks/new", label: "创建任务" },
    ],
  },
  {
    title: "Engineering",
    items: [
      { to: "/doctor", label: "环境诊断" },
      { to: "/rules", label: "规则与配方" },
      { to: "/skills", label: "技能注册" },
      { to: "/logs", label: "日志尾流" },
    ],
  },
  {
    title: "Settings",
    items: [{ to: "/settings", label: "配置快照" }],
  },
];

export function AppSidebar(): JSX.Element {
  const location = useLocation();

  const isItemActive = (to: string): boolean => {
    if (to === "/tasks") {
      return location.pathname === "/tasks" || /^\/tasks\/[^/]+$/.test(location.pathname);
    }
    if (to === "/tasks/new") {
      return location.pathname === "/tasks/new";
    }
    return location.pathname === to || location.pathname.startsWith(`${to}/`);
  };

  return (
    <aside className="pw-sidebar">
      <div className="pw-sidebar-orb" />
      <div className="pw-sidebar-brand">
        <div className="pw-sidebar-monogram">PW</div>
        <h1 className="pw-sidebar-title">PatchWeaver</h1>
        <div className="pw-sidebar-line" />
      </div>
      {navGroups.map((group) => (
        <div key={group.title} className="pw-nav-section">
          <div className="pw-nav-section-title">{group.title}</div>
          <nav className="pw-nav">
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={`pw-nav-link${isItemActive(item.to) ? " active" : ""}`}
              >
                <span className="pw-nav-link-title">{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </div>
      ))}
    </aside>
  );
}
