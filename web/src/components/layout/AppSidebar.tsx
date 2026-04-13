import { NavLink } from "react-router-dom";

const navItems = [
  { to: "/overview", label: "Overview" },
  { to: "/tasks", label: "Tasks" },
  { to: "/doctor", label: "Doctor" },
  { to: "/rules", label: "Rules" },
  { to: "/skills", label: "Skills" },
  { to: "/logs", label: "Logs" },
  { to: "/settings", label: "Settings" },
];

export function AppSidebar(): JSX.Element {
  return (
    <aside className="pw-sidebar">
      <h1 className="pw-sidebar-title">PatchWeaver</h1>
      <p className="pw-sidebar-subtitle">Kernel CVE livepatch control console</p>
      <nav className="pw-nav">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `pw-nav-link${isActive ? " active" : ""}`}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
