import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { MetricCard } from "../../components/cards/MetricCard";
import { CodePanel } from "../../components/code/CodePanel";
import { SectionCard } from "../../components/layout/SectionCard";
import { StatusBadge } from "../../components/status/StatusBadge";
import { useLiveQueryOptions } from "../../hooks/useLiveQueryOptions";
import { fetchDoctor, repairDoctor, runDoctor } from "../../services/doctor";
import type { DoctorCheck, DoctorRepairResult } from "../../types/doctor";
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
  const [repairDialogOpen, setRepairDialogOpen] = useState(false);
  const [modelConfigDialogOpen, setModelConfigDialogOpen] = useState(false);
  const [autoOpenedModelConfigSignature, setAutoOpenedModelConfigSignature] = useState<string | null>(null);
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
      setRepairDialogOpen(true);
      queryClient.invalidateQueries({ queryKey: ["doctor"] });
    },
    onError: () => {
      setRepairDialogOpen(true);
    },
  });

  const report = doctorQuery.data;
  const repairResult = repairMutation.data;
  const modelBackendFailure = report?.checks.find(
    (item) => item.category === "model_backend" && item.name === "bailian_chat" && item.status !== "ok",
  );
  const modelBackendFailureSignature = modelBackendFailure
    ? `${modelBackendFailure.status}:${modelBackendFailure.detail}`
    : null;

  useEffect(() => {
    if (!modelBackendFailure || !modelBackendFailureSignature) {
      setAutoOpenedModelConfigSignature(null);
      return;
    }

    if (autoOpenedModelConfigSignature !== modelBackendFailureSignature) {
      setModelConfigDialogOpen(true);
      setAutoOpenedModelConfigSignature(modelBackendFailureSignature);
    }
  }, [autoOpenedModelConfigSignature, modelBackendFailure, modelBackendFailureSignature]);

  return (
    <div className="pw-grid">
      <SectionCard
        title="环境诊断"
        actions={
          <div className="pw-btn-row">
            {modelBackendFailure ? (
              <button className="pw-btn warn" type="button" onClick={() => setModelConfigDialogOpen(true)}>
                模型配置指引
              </button>
            ) : null}
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
        {doctorQuery.isError ? <div className="pw-note-banner">当前无法获取实时诊断结果，但页面结构已准备好用于联调与验收</div> : null}
        {repairMutation.isError ? <div className="pw-note-banner">环境修复接口调用失败，请查看 API 日志</div> : null}
        {report ? (
          <div className="pw-grid metrics">
            <MetricCard label="检查项总数" value={report.summary.total} />
            <MetricCard label="通过" value={report.summary.ok} />
            <MetricCard label="警告" value={report.summary.warn} />
            <MetricCard label="错误" value={report.summary.error} meta={`报告时间 ${formatTime(report.generated_at)}`} />
          </div>
        ) : null}
      </SectionCard>

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
          <div className="pw-empty">诊断报告可用后，这里会展示项目根目录、工作区、数据库、探测目标内核和当前运行机信息</div>
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
            <div className="pw-empty">实时报告返回后，这里会列出每一条 doctor check 的状态与细节</div>
          )}
        </SectionCard>
        <SectionCard
          title="构建环境快照"
          className="pw-doctor-panel"
        >
          <CodePanel
            title="build_env"
            content={report ? JSON.stringify(report.build_env, null, 2) : undefined}
            emptyText="暂无 build_env 快照"
          />
        </SectionCard>
      </div>

      <SectionCard title="运行机快照">
        <CodePanel
          title="machine_profile"
          content={report?.machine_profile ? JSON.stringify(report.machine_profile, null, 2) : undefined}
          emptyText="暂无 machine_profile 快照"
        />
      </SectionCard>

      {repairDialogOpen ? (
        <RepairResultDialog
          repairResult={repairMutation.isError ? undefined : repairResult}
          hasError={repairMutation.isError}
          onClose={() => setRepairDialogOpen(false)}
        />
      ) : null}

      {modelConfigDialogOpen && modelBackendFailure ? (
        <ModelConfigDialog check={modelBackendFailure} onClose={() => setModelConfigDialogOpen(false)} />
      ) : null}
    </div>
  );
}

type ModelConfigDialogProps = {
  check: DoctorCheck;
  onClose: () => void;
};

function ModelConfigDialog({ check, onClose }: ModelConfigDialogProps): JSX.Element {
  const remediation = normalizeRemediation(check);
  const envVar = remediation.env_var ?? "PATCHWEAVER_BAILIAN_API_KEY";
  const restartCommands = remediation.commands?.length
    ? remediation.commands.join("\n")
    : [
        `export ${envVar}="<your-bailian-api-key>"`,
        "docker restart patchweaver-dev-api",
        "docker restart patchweaver-api",
        "systemctl daemon-reload && systemctl restart patchweaver-api",
      ].join("\n");

  return (
    <div className="pw-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="pw-modal pw-doctor-model-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="doctor-model-config-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="pw-modal-header">
          <div>
            <span className="pw-kicker">Model Backend</span>
            <h3 id="doctor-model-config-dialog-title">模型配置指引</h3>
          </div>
          <button className="pw-icon-btn" type="button" aria-label="关闭模型配置指引" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="pw-section-stack">
          <div className="pw-note-banner">检测到 Bailian Chat 健康检查未通过，请先确认 API 进程可读取环境变量</div>

          <div className="pw-doctor-model-summary">
            <div className="pw-list-item">
              <strong>失败详情</strong>
              <div className="pw-inline-note">检查项: {check.label}</div>
              <div className="pw-inline-note">状态: {check.status}</div>
              <div className="pw-inline-note">{check.detail}</div>
            </div>
            <div className="pw-list-item">
              <strong>环境变量名</strong>
              <code className="pw-doctor-env-name">{envVar}</code>
              <div className="pw-inline-note">只注入运行时环境，不在页面展示真实 key，不要求写入配置文件</div>
            </div>
          </div>

          <RemediationContent remediation={remediation} />

          <div className="pw-step-grid pw-doctor-model-steps">
            <div className="pw-step-card">
              <strong>1. 准备凭据</strong>
              <div className="pw-inline-note">从 Bailian 控制台确认可用 key，保存到本机 shell、Docker env 或 systemd Environment</div>
            </div>
            <div className="pw-step-card">
              <strong>2. 注入 API 运行环境</strong>
              <div className="pw-inline-note">确保启动 API 的进程能读取 {envVar}，避免把真实 key 写入仓库配置</div>
            </div>
            <div className="pw-step-card">
              <strong>3. 重启服务</strong>
              <div className="pw-inline-note">重启 API、Docker 服务或 systemd unit，让新环境变量进入进程</div>
            </div>
            <div className="pw-step-card">
              <strong>4. 重新诊断</strong>
              <div className="pw-inline-note">关闭弹窗后点击重新执行诊断，确认 bailian_chat 状态恢复为 ok</div>
            </div>
          </div>

          <CodePanel title="restart_examples" content={restartCommands} />

          <div className="pw-btn-row">
            <button className="pw-btn primary" type="button" onClick={onClose}>
              关闭
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

type RemediationContentProps = {
  remediation: {
    title: string;
    env_var?: string;
    steps: string[];
    commands: string[];
    notes: string[];
  };
};

function RemediationContent({ remediation }: RemediationContentProps): JSX.Element {
  return (
    <div className="pw-doctor-remediation-grid">
      <div className="pw-list-item">
        <strong>{remediation.title}</strong>
        <div className="pw-list pw-doctor-remediation-list">
          {remediation.steps.map((item) => (
            <div key={item} className="pw-inline-note">
              {item}
            </div>
          ))}
        </div>
      </div>
      {remediation.notes.length > 0 ? (
        <div className="pw-list-item">
          <strong>注意事项</strong>
          <div className="pw-list pw-doctor-remediation-list">
            {remediation.notes.map((item) => (
              <div key={item} className="pw-inline-note">
                {item}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function normalizeRemediation(check: DoctorCheck): RemediationContentProps["remediation"] {
  const fallback = {
    title: "大模型连接配置",
    env_var: String(check.metadata?.api_key_env ?? "PATCHWEAVER_BAILIAN_API_KEY"),
    steps: [
      "在启动 PatchWeaver API 的宿主机或容器环境中设置环境变量",
      "重启 API 服务或 Docker 容器，让新环境变量进入进程环境",
      "回到环境诊断页面，点击重新执行诊断确认模型响应正常",
    ],
    commands: [
      `export ${String(check.metadata?.api_key_env ?? "PATCHWEAVER_BAILIAN_API_KEY")}="<your-bailian-api-key>"`,
      "docker restart patchweaver-dev-api",
      "docker restart patchweaver-api",
      "systemctl daemon-reload && systemctl restart patchweaver-api",
    ],
    notes: ["不要把 API Key 写入仓库或报告"],
  };

  const value = check.remediation;
  if (!value) {
    return fallback;
  }
  if (typeof value === "string") {
    return { ...fallback, steps: [value] };
  }
  if (Array.isArray(value)) {
    return { ...fallback, steps: value };
  }
  return {
    title: value.title ?? fallback.title,
    env_var: value.env_var ?? fallback.env_var,
    steps: value.steps?.length ? value.steps : fallback.steps,
    commands: value.commands?.length ? value.commands : fallback.commands,
    notes: value.notes ?? fallback.notes,
  };
}

type RepairResultDialogProps = {
  repairResult?: DoctorRepairResult;
  hasError: boolean;
  onClose: () => void;
};

function RepairResultDialog({ repairResult, hasError, onClose }: RepairResultDialogProps): JSX.Element {
  return (
    <div className="pw-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="pw-modal pw-doctor-repair-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="doctor-repair-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="pw-modal-header">
          <div>
            <span className="pw-kicker">Repair Result</span>
            <h3 id="doctor-repair-dialog-title">修复结果</h3>
          </div>
          <button className="pw-icon-btn" type="button" aria-label="关闭修复结果弹窗" onClick={onClose}>
            ×
          </button>
        </div>

        {hasError && !repairResult ? (
          <div className="pw-note-banner">环境修复接口调用失败，请查看 API 日志</div>
        ) : null}

        {repairResult ? (
          <div className="pw-section-stack">
            <div className="pw-grid metrics">
              <MetricCard label="修复状态" value={repairResult.status} />
              <MetricCard label="错误数变化" value={`${repairResult.summary.before.error} -> ${repairResult.summary.after.error}`} />
              <MetricCard label="剩余错误" value={repairResult.summary.remaining_error_count} />
              <MetricCard label="脚本路径" value={repairResult.script.path ?? "未生成"} />
            </div>

            {repairResult.remaining_errors.length > 0 ? (
              <div className="pw-note-banner">
                仍有 {repairResult.remaining_errors.length} 个错误未解除，需要检查宿主机依赖或重新部署容器
              </div>
            ) : (
              <div className="pw-note-banner">本轮修复后未发现剩余错误</div>
            )}

            <div className="pw-doctor-repair-grid">
              <div className="pw-list">
                {repairResult.actions.map((item) => (
                  <div key={`${item.name}-${item.path ?? item.status}`} className="pw-list-item">
                    <strong>{item.label}</strong>
                    <div className="pw-inline-note">状态: {item.status}</div>
                    <div className="pw-inline-note">{item.detail}</div>
                    {item.path ? <div className="pw-inline-note">路径: {item.path}</div> : null}
                    {item.executed !== undefined ? <div className="pw-inline-note">已执行: {item.executed ? "是" : "否"}</div> : null}
                    {item.stdout_excerpt ? <div className="pw-inline-note">输出: {item.stdout_excerpt}</div> : null}
                    {item.stderr_excerpt ? <div className="pw-inline-note">错误输出: {item.stderr_excerpt}</div> : null}
                  </div>
                ))}
              </div>
              <CodePanel title="repair_docker_web_environment.sh" content={repairResult.script.content} emptyText="暂无修复脚本" />
            </div>

            <div className="pw-btn-row">
              <button className="pw-btn primary" type="button" onClick={onClose}>
                知道了
              </button>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
