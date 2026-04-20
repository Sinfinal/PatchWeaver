import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MetricCard } from "../../components/cards/MetricCard";
import { CodePanel } from "../../components/code/CodePanel";
import { SectionCard } from "../../components/layout/SectionCard";
import { StatusBadge } from "../../components/status/StatusBadge";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { fetchDoctor, runDoctor } from "../../services/doctor";

const runtimeLabelMap: Record<string, string> = {
  project_root: "项目根目录",
  workspace_root: "工作区根目录",
  database_path: "数据库路径",
  manifest_dir: "Manifest 目录",
  default_kernel: "默认内核",
  max_attempts: "默认最大尝试轮数",
  python_version: "Python 版本",
};

export function DoctorPage(): JSX.Element {
  const queryClient = useQueryClient();
  const liveQueryOptions = useLiveQueryOptions();
  const doctorQuery = useQuery({
    queryKey: ["doctor"],
    queryFn: fetchDoctor,
    ...liveQueryOptions,
  });
  const doctorMutation = useMutation({
    mutationFn: runDoctor,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["doctor"] });
    },
  });

  const report = doctorQuery.data;

  return (
    <div className="pw-grid">
      <SectionCard
        title="环境诊断"
        subtitle="对工作区、数据库、默认内核、Python 运行时和构建环境做统一自检。"
        actions={
          <button className="pw-btn primary" type="button" onClick={() => doctorMutation.mutate()}>
            重新执行诊断
          </button>
        }
      >
        {doctorQuery.isLoading ? <div className="pw-note-banner">正在加载环境诊断报告...</div> : null}
        {doctorQuery.isError ? <div className="pw-note-banner">当前无法获取实时诊断结果，但页面结构已准备好用于联调与验收。</div> : null}
        {report ? (
          <div className="pw-grid metrics">
            <MetricCard label="检查项总数" value={report.summary.total} />
            <MetricCard label="通过" value={report.summary.ok} />
            <MetricCard label="警告" value={report.summary.warn} />
            <MetricCard label="错误" value={report.summary.error} meta={`报告时间 ${report.generated_at}`} />
          </div>
        ) : null}
      </SectionCard>

      <SectionCard title="运行时路径与默认值" subtitle="这一部分最适合用于确认“我到底连的是哪套环境”。">
        {report ? (
          <div className="pw-kv">
            {Object.entries(report.runtime).map(([key, value]) => (
              <div key={key} className="pw-kv-item">
                <span className="pw-kv-label">{runtimeLabelMap[key] ?? key}</span>
                <div className="pw-kv-value">{String(value)}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="pw-empty">诊断报告可用后，这里会展示项目根目录、工作区、数据库与默认内核等关键信息。</div>
        )}
      </SectionCard>

      <div className="pw-grid two pw-doctor-grid">
        <SectionCard
          title="检查项明细"
          subtitle="适合在联调时快速识别是 warning 还是 hard error。"
          className="pw-doctor-panel"
        >
          {report ? (
            <table className="pw-table">
              <thead>
                <tr>
                  <th>检查项</th>
                  <th>状态</th>
                  <th>详情</th>
                </tr>
              </thead>
              <tbody>
                {report.checks.map((item) => (
                  <tr key={`${item.category}-${item.name}`}>
                    <td>{item.label}</td>
                    <td>
                      <StatusBadge value={item.status} />
                    </td>
                    <td>{item.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="pw-empty">实时报告返回后，这里会列出每一条 doctor check 的状态与细节。</div>
          )}
        </SectionCard>
        <SectionCard
          title="构建环境快照"
          subtitle="便于确认远端构建机或本地 build 环境到底返回了什么。"
          className="pw-doctor-panel"
        >
          <CodePanel
            title="build_env"
            content={report ? JSON.stringify(report.build_env, null, 2) : undefined}
            emptyText="暂无 build_env 快照。"
          />
        </SectionCard>
      </div>
    </div>
  );
}
