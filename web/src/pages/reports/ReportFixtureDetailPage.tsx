import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { CodePanel } from "../../components/code/CodePanel";
import { SectionCard } from "../../components/layout/SectionCard";
import { StatusBadge } from "../../components/status/StatusBadge";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { fetchEvaluationFixtureDetail } from "../../services/reports";
import { shortenPath } from "../../utils/format";

export function ReportFixtureDetailPage(): JSX.Element {
  const params = useParams<{ fixtureGroup: string; fixtureId: string }>();
  const fixtureGroup = params.fixtureGroup ?? "";
  const fixtureId = params.fixtureId ?? "";
  const liveQueryOptions = useLiveQueryOptions();
  const query = useQuery({
    queryKey: ["fixture-detail", fixtureGroup, fixtureId],
    queryFn: () => fetchEvaluationFixtureDetail(fixtureGroup, fixtureId),
    enabled: fixtureGroup.length > 0 && fixtureId.length > 0,
    ...liveQueryOptions,
  });

  if (query.isLoading) {
    return <div className="pw-empty">正在加载样例详情...</div>;
  }

  if (query.isError || !query.data) {
    return <div className="pw-empty">当前无法读取样例详情，请确认分组和 fixture_id 是否正确。</div>;
  }

  const payload = query.data;
  const taskStatus = typeof payload.detail.task_status === "string" ? payload.detail.task_status : undefined;

  return (
    <div className="pw-grid">
      <SectionCard
        title={payload.fixture_id}
        actions={
          <div className="pw-btn-row">
            <Link className="pw-btn" to={`/reports/fixtures/${payload.fixture_group}`}>
              返回分组页
            </Link>
            {payload.detail.task_id ? (
              <Link className="pw-btn" to={`/reports/tasks/${payload.detail.task_id}`}>
                打开任务报告
              </Link>
            ) : null}
          </div>
        }
      >
        <div className="pw-kv">
          <div className="pw-kv-item">
            <span className="pw-kv-label">任务状态</span>
            <div className="pw-kv-value">
              <StatusBadge value={taskStatus ?? "missing"} />
            </div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">任务编号</span>
            <div className="pw-kv-value">{String(payload.detail.task_id ?? "未匹配")}</div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">CVE</span>
            <div className="pw-kv-value">{String(payload.detail.cve_id ?? "未记录")}</div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">目标内核</span>
            <div className="pw-kv-value">{String(payload.detail.target_kernel ?? "未记录")}</div>
          </div>
          <div className="pw-kv-item">
            <span className="pw-kv-label">详情文件</span>
            <div className="pw-kv-value">{shortenPath(payload.detail_path)}</div>
          </div>
        </div>
      </SectionCard>

      <div className="pw-grid two">
        <SectionCard title="任务摘要">
          <CodePanel
            title="task_summary"
            content={payload.detail.task_summary ? JSON.stringify(payload.detail.task_summary, null, 2) : undefined}
            emptyText="当前没有 task_summary。"
          />
        </SectionCard>
        <SectionCard title="回放对比摘要">
          <CodePanel
            title="replay_comparison"
            content={
              payload.detail.replay_comparison ? JSON.stringify(payload.detail.replay_comparison, null, 2) : undefined
            }
            emptyText="当前没有 replay_comparison。"
          />
        </SectionCard>
      </div>

      <SectionCard title="原始样例详情">
        <CodePanel
          title="fixture_detail.json"
          path={payload.detail_path}
          content={JSON.stringify(payload.detail, null, 2)}
          emptyText="当前没有样例详情内容。"
        />
      </SectionCard>
    </div>
  );
}
