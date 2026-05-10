import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { TaskCreateForm } from "../../components/forms/TaskCreateForm";
import { SectionCard } from "../../components/layout/SectionCard";
import { architectureStages, buildProfiles } from "../../content/projectContent";
import { createTask } from "../../services/tasks";
import type { CreateTaskPayload } from "../../types/tasks";

export function TaskCreatePage(): JSX.Element {
  const navigate = useNavigate();
  const createMutation = useMutation({
    mutationFn: (payload: CreateTaskPayload) => createTask(payload),
    onSuccess: (data) => {
      navigate(`/tasks/${data.task.task_id}`);
    },
  });

  return (
    <div className="pw-grid detail">
      <SectionCard title="创建任务">
        <TaskCreateForm submitting={createMutation.isPending} onSubmit={createMutation.mutateAsync} />
        {createMutation.isError ? <div className="pw-empty">任务创建失败，请检查后端返回的错误信息或配置状态。</div> : null}
      </SectionCard>

      <div className="pw-grid">
        <SectionCard title="推荐默认值">
          <div className="pw-list">
            <div className="pw-list-item">
              <strong>目标内核</strong>
              <div className="pw-inline-note">6.6.102-5.2.an23.x86_64</div>
            </div>
            <div className="pw-list-item">
              <strong>推荐档位</strong>
              <div className="pw-inline-note">首次联调优先使用 `demo`，本地快速排错可切到 `dev`。</div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="Profile 说明">
          <div className="pw-list">
            {buildProfiles.map((profile) => (
              <div key={profile.name} className="pw-list-item">
                <strong>
                  {profile.name} · {profile.attempts}
                </strong>
                <div className="pw-inline-note">{profile.description}</div>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="任务会经过什么">
          <div className="pw-list">
            {architectureStages.slice(0, 4).map((stage) => (
              <div key={stage.id} className="pw-list-item">
                <strong>{stage.title}</strong>
                <div className="pw-inline-note">{stage.description}</div>
              </div>
            ))}
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
