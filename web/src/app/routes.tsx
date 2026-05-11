import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { Navigate } from "react-router-dom";
import { DoctorPage } from "../pages/doctor/DoctorPage";
import { LogsPage } from "../pages/logs/LogsPage";
import { OverviewPage } from "../pages/overview/OverviewPage";
import { ReportFixtureDetailPage } from "../pages/reports/ReportFixtureDetailPage";
import { ReportFixtureGroupPage } from "../pages/reports/ReportFixtureGroupPage";
import { ReportsPage } from "../pages/reports/ReportsPage";
import { ReportTaskPage } from "../pages/reports/ReportTaskPage";
import { RulesPage } from "../pages/rules/RulesPage";
import { SettingsPage } from "../pages/settings/SettingsPage";
import { SkillsPage } from "../pages/skills/SkillsPage";
import { TaskDetailPage } from "../pages/tasks/TaskDetailPage";
import { TaskListPage } from "../pages/tasks/TaskListPage";

// 打包部署到 /console 时，这里要和 Vite 的 base 保持一致，
// 否则浏览器刷新或静态资源加载会回到站点根路径
const routerBase = import.meta.env.BASE_URL.replace(/\/$/, "");

export const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <AppShell />,
      children: [
        { index: true, element: <OverviewPage /> },
        { path: "overview", element: <OverviewPage /> },
        { path: "tasks", element: <TaskListPage /> },
        { path: "tasks/new", element: <Navigate to="/tasks" replace /> },
        { path: "tasks/:taskId", element: <TaskDetailPage /> },
        { path: "reports", element: <ReportsPage /> },
        { path: "reports/tasks/:taskId", element: <ReportTaskPage /> },
        { path: "reports/fixtures/:fixtureGroup", element: <ReportFixtureGroupPage /> },
        { path: "reports/fixtures/:fixtureGroup/:fixtureId", element: <ReportFixtureDetailPage /> },
        { path: "doctor", element: <DoctorPage /> },
        { path: "rules", element: <RulesPage /> },
        { path: "skills", element: <SkillsPage /> },
        { path: "logs", element: <LogsPage /> },
        { path: "settings", element: <SettingsPage /> },
      ],
    },
  ],
  {
    basename: routerBase,
  },
);
