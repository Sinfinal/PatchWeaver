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
  });

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await onSubmit(form);
  }

  return (
    <form className="pw-form" onSubmit={handleSubmit}>
      <div className="pw-field">
        <label htmlFor="cve-id">CVE 编号</label>
        <input
          id="cve-id"
          className="pw-input"
          value={form.cve_id ?? ""}
          onChange={(event) => setForm((current) => ({ ...current, cve_id: event.target.value }))}
          placeholder="例如：CVE-2024-1086"
          required
        />
      </div>
      <div className="pw-field">
        <label htmlFor="target-kernel">目标内核</label>
        <input
          id="target-kernel"
          className="pw-input"
          value={form.target_kernel ?? ""}
          onChange={(event) => setForm((current) => ({ ...current, target_kernel: event.target.value }))}
          placeholder="不填则走系统默认值"
        />
      </div>
      <div className="pw-field">
        <label htmlFor="profile">运行档位</label>
        <select
          id="profile"
          className="pw-select"
          value={form.profile ?? "demo"}
          onChange={(event) => setForm((current) => ({ ...current, profile: event.target.value }))}
        >
          <option value="dev">dev</option>
          <option value="demo">demo</option>
          <option value="full">full</option>
        </select>
      </div>
      <div className="pw-field">
        <label htmlFor="max-attempts">最大尝试轮次</label>
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
          placeholder="不填则按 profile 继承"
        />
      </div>
      <div className="pw-field">
        <label htmlFor="note">备注</label>
        <textarea
          id="note"
          className="pw-textarea"
          value={form.note ?? ""}
          onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))}
          placeholder="记录样例来源、负责人或当前关注点"
        />
      </div>
      <div className="pw-btn-row">
        <button className="pw-btn primary" type="submit" disabled={submitting}>
          {submitting ? "创建中..." : "创建任务"}
        </button>
      </div>
    </form>
  );
}
