import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { TaskCreateForm } from "../../components/forms/TaskCreateForm";
import { SectionCard } from "../../components/layout/SectionCard";
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
    <div className="pw-grid">
      <SectionCard title="新建任务" subtitle="创建任务、初始化工作区，并进入详情页继续分析和构建">
        <TaskCreateForm submitting={createMutation.isPending} onSubmit={createMutation.mutateAsync} />
        {createMutation.isError ? <div className="pw-empty">任务创建失败，请检查输入或后端日志。</div> : null}
      </SectionCard>
    </div>
  );
}
