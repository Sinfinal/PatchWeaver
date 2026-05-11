import { useState, type FormEvent } from "react";
import type { CreateTaskPayload } from "../../types/tasks";

type TaskCreateFormProps = {
  submitting: boolean;
  onSubmit: (payload: CreateTaskPayload) => Promise<unknown>;
};

export function TaskCreateForm({ submitting, onSubmit }: TaskCreateFormProps): JSX.Element {
  const [form, setForm] = useState<CreateTaskPayload>({
    cve_id: "",
    profile: "demo",
    target_kernel: "",
    force_new: false,
    auto_run: true,
  });

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await onSubmit({
      ...form,
      cve_id: form.cve_id.trim(),
      target_kernel: form.target_kernel?.trim() || undefined,
      note: form.note?.trim() || undefined,
    });
  }

  return (
    <form className="pw-form" onSubmit={handleSubmit}>
      <div className="pw-field">
        <label htmlFor="cve-id">CVE ID</label>
        <input
          id="cve-id"
          className="pw-input"
          value={form.cve_id ?? ""}
          onChange={(event) => setForm((current) => ({ ...current, cve_id: event.target.value }))}
          placeholder="例如 CVE-2024-1086"
          required
        />
        <div className="pw-field-hint">输入单个 CVE 编号，系统会围绕它拉取 patch、分析上下文并生成工作区</div>
      </div>
      <div className="pw-field">
        <label htmlFor="target-kernel">目标内核版本</label>
        <input
          id="target-kernel"
          className="pw-input"
          value={form.target_kernel ?? ""}
          onChange={(event) => setForm((current) => ({ ...current, target_kernel: event.target.value }))}
          placeholder="留空则按当前运行机与构建环境自动探测"
        />
        <div className="pw-field-hint">通常建议留空，系统会优先根据当前运行机和可用构建环境自动绑定目标内核；只有明确需要覆盖时再手工填写</div>
      </div>
      <div className="pw-field">
        <label htmlFor="profile">运行档位</label>
        <select
          id="profile"
          className="pw-select"
          value={form.profile ?? "demo"}
          onChange={(event) => setForm((current) => ({ ...current, profile: event.target.value }))}
        >
          <option value="dev">dev - 快速调试</option>
          <option value="demo">demo - 演示推荐</option>
          <option value="full">full - 完整运行</option>
        </select>
        <div className="pw-field-hint">`dev` 最快，`demo` 适合联调展示，`full` 更适合正式跑样例与稳定验证</div>
      </div>
      <div className="pw-field">
        <label htmlFor="max-attempts">最大尝试轮数</label>
        <input
          id="max-attempts"
          className="pw-input"
          type="number"
          min={1}
          max={10}
          value={form.max_attempts ?? ""}
          onChange={(event) =>
            setForm((current) => ({
              ...current,
              max_attempts: event.target.value ? Number(event.target.value) : undefined,
            }))
          }
          placeholder="留空则采用当前 profile 默认值"
        />
        <div className="pw-field-hint">建议只在明确想控制尝试上限时填写，常规情况下让 profile 默认值接管即可</div>
      </div>
      <div className="pw-field">
        <label htmlFor="note">任务备注</label>
        <textarea
          id="note"
          className="pw-textarea"
          value={form.note ?? ""}
          onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))}
          placeholder="可记录样例来源、联调目标、需要重点关注的规则或失败类型"
        />
        <div className="pw-field-hint">备注会进入任务上下文，适合记录“为什么要跑这条样例”</div>
      </div>
      <label className="pw-check-row">
        <input
          type="checkbox"
          checked={Boolean(form.force_new)}
          onChange={(event) => setForm((current) => ({ ...current, force_new: event.target.checked }))}
        />
        <span>已有同配置任务时仍创建新任务</span>
      </label>
      <div className="pw-field-hint">默认会复用最近一次同配置任务；勾选后用于重新验证同一个 CVE</div>
      <label className="pw-check-row">
        <input
          type="checkbox"
          checked={Boolean(form.auto_run)}
          onChange={(event) => setForm((current) => ({ ...current, auto_run: event.target.checked }))}
        />
        <span>创建后自动运行主链</span>
      </label>
      <div className="pw-field-hint">开启后由 Agent 受控动作推进 analyze、run、report、replay，任务详情会持续读取同一份状态</div>
      <div className="pw-btn-row">
        <button className="pw-btn primary" type="submit" disabled={submitting}>
          {submitting ? "正在创建..." : "创建任务"}
        </button>
      </div>
    </form>
  );
}
