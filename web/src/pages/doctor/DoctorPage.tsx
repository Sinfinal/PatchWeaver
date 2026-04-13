import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SectionCard } from "../../components/layout/SectionCard";
import { MetricCard } from "../../components/cards/MetricCard";
import { runDoctor, fetchDoctor } from "../../services/doctor";
import { StatusBadge } from "../../components/status/StatusBadge";

export function DoctorPage(): JSX.Element {
  const queryClient = useQueryClient();
  const doctorQuery = useQuery({
    queryKey: ["doctor"],
    queryFn: fetchDoctor,
  });
  const doctorMutation = useMutation({
    mutationFn: runDoctor,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["doctor"] });
    },
  });

  if (doctorQuery.isLoading) {
    return <div className="pw-empty">诊断数据加载中...</div>;
  }

  if (doctorQuery.isError || !doctorQuery.data) {
    return <div className="pw-empty">诊断数据加载失败。</div>;
  }

  const report = doctorQuery.data;
  return (
    <div className="pw-grid">
      <SectionCard
        title="环境诊断"
        subtitle={`最近生成时间：${report.generated_at}`}
        actions={
          <button className="pw-btn primary" type="button" onClick={() => doctorMutation.mutate()}>
            重新执行 doctor
          </button>
        }
      >
        <div className="pw-grid metrics">
          <MetricCard label="检查总数" value={report.summary.total} />
          <MetricCard label="正常项" value={report.summary.ok} />
          <MetricCard label="提示项" value={report.summary.warn} />
          <MetricCard label="错误项" value={report.summary.error} />
        </div>
      </SectionCard>

      <SectionCard title="运行时信息" subtitle="当前控制台绑定的本地运行环境">
        <div className="pw-kv">
          {Object.entries(report.runtime).map(([key, value]) => (
            <div key={key} className="pw-kv-item">
              <span className="pw-kv-label">{key}</span>
              <div className="pw-kv-value">{String(value)}</div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="检查项" subtitle="覆盖 Python、配置、目录与构建后端">
        <table className="pw-table">
          <thead>
            <tr>
              <th>Label</th>
              <th>Status</th>
              <th>Detail</th>
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
      </SectionCard>
    </div>
  );
}
