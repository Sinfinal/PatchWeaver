import { Outlet } from "react-router-dom";
import { AppHeader } from "./AppHeader";
import { AppSidebar } from "./AppSidebar";

export function AppShell(): JSX.Element {
  return (
    <div className="pw-shell">
      <AppSidebar />
      <main className="pw-main">
        <AppHeader />
        <Outlet />
      </main>
    </div>
  );
}
