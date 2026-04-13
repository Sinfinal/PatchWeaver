export type TaskListItem = {
  task_id: string;
  cve_id: string;
  target_kernel: string;
  status: string;
  current_attempt: number;
  max_attempts: number;
  workspace_dir: string;
  created_at: string;
  updated_at: string;
  latest_failure_type?: string | null;
  latest_failure_summary?: string | null;
  attempts_count: number;
};

export type TaskListResponse = {
  items: TaskListItem[];
  total: number;
};

export type TaskSummary = {
  task_id: string;
  cve_id: string;
  target_kernel: string;
  status: string;
  current_attempt: number;
  max_attempts: number;
  workspace_dir: string;
  created_at: string;
  updated_at: string;
};

export type TaskAttempt = {
  attempt_id: string;
  attempt_no: number;
  status: string;
  failure_type?: string | null;
  build_log_path?: string | null;
  module_path?: string | null;
  rewritten_patch_path?: string | null;
  started_at: string;
  finished_at?: string | null;
  failure_record_path: string;
  validation_report_path: string;
  harness_trace_path: string;
  rewrite_plan_path: string;
};

export type TimelineNode = {
  stage: string;
  status: string;
  path?: string | null;
};

export type ArtifactIndexItem = {
  artifact_type: string;
  artifact_path: string;
  relative_path: string;
  summary: string;
};

export type ReplayPayload = {
  latest_attempt_id?: string | null;
  latest_attempt_status?: string | null;
  trace_path?: string | null;
  report_path?: string | null;
  stage_routes: Record<string, unknown>;
  dispatch_modes: Record<string, unknown>;
  replay_files: string[];
  status: string;
};

export type TaskDetailResponse = {
  task: TaskSummary;
  patch_bundle?: Record<string, unknown> | null;
  analysis: {
    semantic_card_path: string;
    constraint_report_path: string;
    context_bundle_path: string;
    analysis_trace_path: string;
  };
  attempts: TaskAttempt[];
  latest_failure?: Record<string, unknown> | null;
  latest_validation?: Record<string, unknown> | null;
  latest_trace?: Record<string, unknown> | null;
  latest_rewrite_plan?: Record<string, unknown> | null;
  reports: {
    json_path: string;
    md_path: string;
  };
  replay: ReplayPayload;
  timeline: TimelineNode[];
  artifact_index: ArtifactIndexItem[];
  workspace_exists: boolean;
};

export type CreateTaskPayload = {
  cve_id: string;
  target_kernel?: string;
  profile?: string;
  max_attempts?: number;
  note?: string;
};

export type TaskActionResponse = {
  task_id: string;
  status: string;
  detail: Record<string, unknown>;
};

export type ArtifactTreeNode = {
  name: string;
  relative_path: string;
  kind: "file" | "directory";
  size?: number | null;
  suffix?: string;
  children?: ArtifactTreeNode[];
};

export type ArtifactTreeResponse = {
  task_id: string;
  root: string;
  tree: ArtifactTreeNode[];
  items: Array<{
    name: string;
    relative_path: string;
    kind: "file" | "directory";
    size?: number | null;
    suffix?: string;
  }>;
};

export type ArtifactContentResponse = {
  task_id: string;
  relative_path: string;
  absolute_path: string;
  content: string;
  content_type: string;
  truncated: boolean;
  size?: number | null;
};
