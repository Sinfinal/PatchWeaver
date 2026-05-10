import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MetricCard } from "../../components/cards/MetricCard";
import { CodePanel } from "../../components/code/CodePanel";
import { SectionCard } from "../../components/layout/SectionCard";
import { StatusBadge } from "../../components/status/StatusBadge";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { fetchDoctor, repairDoctor, runDoctor } from "../../services/doctor";
import { formatTime } from "../../utils/format";

const runtimeLabelMap: Record<string, string> = {
  project_root: "项目根目录",
  workspace_root: "工作区根目录",
  database_path: "数据库路径",
  manifest_dir: "Manifest 目录",
  configured_default_kernel: "配置默认内核",
  detected_target_kernel: "探测目标内核",
  detected_target_kernel_source: "探测来源",
  machine_kernel: "当前运行机内核",
  machine_arch: "当前运行机架构",
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
  const repairMutation = useMutation({
    mutationFn: repairDoctor,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["doctor"] });
    },
  });

  const report = doctorQuery.data;
  const repairResult = repairMutation.data;

  return (
    <div className="pw-grid">
      <SectionCard
        title="环境诊断"
        actions={
          <div className="pw-btn-row">
            <button className="pw-btn" type="button" onClick={() => doctorMutation.mutate()} disabled={doctorMutation.isPending}>
              {doctorMutation.isPending ? "诊断中..." : "重新执行诊断"}
            </button>
            <button className="pw-btn primary" type="button" onClick={() => repairMutation.mutate()} disabled={repairMutation.isPending}>
              {repairMutation.isPending ? "修复中..." : "一键修复环境"}
            </button>
          </div>
        }
      >
        {doctorQuery.isLoading ? <div className="pw-note-banner">正在加载环境诊断报告...</div> : null}
        {doctorQuery.isError ? <div className="pw-note-banner">当前无法获取实时诊断结果，但页面结构已准备好用于联调与验收。</div> : null}
        {repairMutation.isError ? <div className="pw-note-banner">环境修复接口调用失败，请查看 API 日志。</div> : null}
        {report ? (
          <div className="pw-grid metrics">
            <MetricCard label="检查项总数" value={report.summary.total} />
            <MetricCard label="通过" value={report.summary.ok} />
            <MetricCard label="警告" value={report.summary.warn} />
            <MetricCard label="错误" value={report.summary.error} meta={`报告时间 ${formatTime(report.generated_at)}`} />
          </div>
        ) : null}
      </SectionCard>

      {repairResult ? (
        <SectionCard title="修复结果">
          <div className="pw-grid metrics">
            <MetricCard label="修复状态" value={repairResult.status} />
            <MetricCard label="错误数变化" value={`${repairResult.summary.before.error} -> ${repairResult.summary.after.error}`} />
            <MetricCard label="剩余错误" value={repairResult.summary.remaining_error_count} />
            <MetricCard label="脚本路径" value={repairResult.script.path ?? "未生成"} />
          </div>
          <div className="pw-grid two" style={{ marginTop: 16 }}>
            <div className="pw-list">
              {repairResult.actions.map((item) => (
                <div key={`${item.name}-${item.path ?? item.status}`} className="pw-list-item">
                  <strong>{item.label}</strong>
                  <div className="pw-inline-note">状态: {item.status}</div>
                  <div className="pw-inline-note">{item.detail}</div>
                  {item.path ? <div className="pw-inline-note">路径: {item.path}</div> : null}
                </div>
              ))}
            </div>
            <CodePanel title="repair_docker_web_environment.sh" content={repairResult.script.content} emptyText="暂无修复脚本。" />
          </div>
        </SectionCard>
      ) : null}

      <SectionCard title="运行时路径与默认值">
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
          <div className="pw-empty">诊断报告可用后，这里会展示项目根目录、工作区、数据库、探测目标内核和当前运行机信息。</div>
        )}
      </SectionCard>

      <div className="pw-grid two pw-doctor-grid">
        <SectionCard
          title="检查项明细"
          className="pw-doctor-panel"
        >
          {report ? (
            <div className="pw-table-shell">
              <table className="pw-table pw-doctor-table">
                <thead>
                  <tr>
                    <th className="pw-cell-no-wrap">检查项</th>
                    <th className="pw-cell-no-wrap">状态</th>
                    <th>详情</th>
                  </tr>
                </thead>
                <tbody>
                  {report.checks.map((item) => (
                    <tr key={`${item.category}-${item.name}`}>
                      <td className="pw-cell-no-wrap">{item.label}</td>
                      <td className="pw-cell-no-wrap">
                        <StatusBadge value={item.status} />
                      </td>
                      <td>{item.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="pw-empty">实时报告返回后，这里会列出每一条 doctor check 的状态与细节。</div>
          )}
        </SectionCard>
        <SectionCard
          title="构建环境快照"
          className="pw-doctor-panel"
        >
          <CodePanel
            title="build_env"
            content={report ? JSON.stringify(report.build_env, null, 2) : undefined}
            emptyText="暂无 build_env 快照。"
          />
        </SectionCard>
      </div>

      <SectionCard title="运行机快照">
        <CodePanel
          title="machine_profile"
          content={report?.machine_profile ? JSON.stringify(report.machine_profile, null, 2) : undefined}
          emptyText="暂无 machine_profile 快照。"
        />
      </SectionCard>
    </div>
  );
}
