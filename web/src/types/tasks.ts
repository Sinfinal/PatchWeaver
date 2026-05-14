export type MachineProfile = {
  machine_system?: string | null;
  machine_kernel?: string | null;
  machine_arch?: string | null;
  hostname?: string | null;
  build_target_kernel?: string | null;
  build_target_kernel_source?: string | null;
  build_backend?: string | null;
  builder_cmd?: string | null;
  builder_path?: string | null;
  selected_source_dir?: string | null;
  selected_source_reason?: string | null;
  config_path?: string | null;
  vmlinux_path?: string | null;
  detected_at?: string | null;
};

export type TaskListItem = {
  task_id: string;
  cve_id: string;
  target_kernel: string;
  target_kernel_source?: string | null;
  status: string;
  current_attempt: number;
  max_attempts: number;
  workspace_dir: string;
  created_at: string;
  updated_at: string;
  latest_failure_type?: string | null;
  latest_failure_summary?: string | null;
  latest_failure_explanation?: string | null;
  latest_failure_explanation_source?: string | null;
  latest_build_exec_status?: string | null;
  latest_target_state?: string | null;
  attempts_count: number;
  fixture_group?: string | null;
  fixture_id?: string | null;
  agent_health?: AgentHealth | null;
};

export type TaskListResponse = {
  items: TaskListItem[];
  total: number;
  limit: number;
  offset: number;
  page: number;
  page_count: number;
  has_prev: boolean;
  has_next: boolean;
};

export type TaskSummary = {
  task_id: string;
  cve_id: string;
  target_kernel: string;
  target_kernel_source?: string | null;
  profile_name?: string | null;
  status: string;
  current_attempt: number;
  max_attempts: number;
  workspace_dir: string;
  machine_profile?: MachineProfile | null;
  created_at: string;
  updated_at: string;
  latest_failure_type?: string | null;
  latest_build_exec_status?: string | null;
  latest_target_state?: string | null;
  agent_health?: AgentHealth | null;
  fixture_group?: string | null;
  fixture_id?: string | null;
};

export type TaskAttempt = {
  attempt_id: string;
  attempt_no: number;
  status: string;
  failure_type?: string | null;
  build_exec_status?: string | null;
  target_state?: string | null;
  build_log_path?: string | null;
  module_path?: string | null;
  rewritten_patch_path?: string | null;
  started_at: string;
  finished_at?: string | null;
  failure_record_path: string;
  validation_report_path: string;
  validation_matrix_path: string;
  semantic_guard_path: string;
  planning_hints_path: string;
  harness_trace_path: string;
  rewrite_plan_path: string;
};

export type TimelineNode = {
  stage: string;
  status: string;
  path?: string | null;
  label?: string;
  current_effect?: string;
  missing_effect?: string;
  problem?: string | null;
  analysis?: string;
  next_action?: string;
  evidence_paths?: string[];
  primary_evidence_path?: string | null;
};

export type StageViewNode = TimelineNode & {
  label: string;
  current_effect: string;
  missing_effect: string;
  problem?: string | null;
  analysis: string;
  next_action: string;
  evidence_paths: string[];
  primary_evidence_path?: string | null;
};

export type ProcessSummary = {
  overall_status: string;
  current_stage: string;
  headline: string;
  reached_effect: string;
  missing_effect: string;
  problem?: string | null;
  analysis: string;
  next_action: string;
  primary_evidence_path?: string | null;
  current_attempt_no?: number | null;
  latest_failure_type?: string | null;
  latest_build_exec_status?: string | null;
  latest_target_state?: string | null;
  replay_status?: string | null;
  state_conflicts: string[];
};

export type AgentDecisionSummary = {
  task_id: string;
  attempt_id?: string | null;
  attempt_no?: number | null;
  repair_intent?: Record<string, unknown> | null;
  selected_recipe?: string | null;
  selected_strategy?: string | null;
  strategy?: string | null;
  strategy_switch: {
    repair_intent_strategy?: string | null;
    selected_recipe?: string | null;
    selected_strategy?: string | null;
    final_strategy?: string | null;
    switched: boolean;
    reason?: string | null;
  };
  agent_next_action?: string | null;
  workflow_trace?: {
    present?: boolean;
    trace_path?: string | null;
    decision_count?: number;
    latest_decision?: {
      selected_action?: string;
      reason?: string;
      terminal?: boolean;
      retry?: boolean;
      risk?: string;
    } | null;
    terminal_stop_reason?: string | null;
  };
  failure_type?: string | null;
  failure_record: {
    summary?: string | null;
    stage_name?: string | null;
    failure_type?: string | null;
    evidence: unknown[];
    diagnostic_details?: unknown;
    raw?: Record<string, unknown> | null;
  };
  diagnostic_details?: unknown;
  state_conflicts: string[];
  source_paths: Record<string, string | null | undefined>;
  source_exists: Record<string, boolean>;
};

export type AgentHealthStatus = "healthy" | "stale" | "evidence_missing" | "terminal" | "unknown" | "retry_loop";

export type AgentHealth = {
  task_id: string;
  status: AgentHealthStatus;
  signals: string[];
  recommendations: string[];
  latest_failure_type?: string | null;
  latest_attempt_no?: number | null;
  latest_trace_decision_count?: number;
  checked_at: string;
  evidence: Array<{
    path: string | null;
    exists: boolean;
    mtime?: string | null;
  }>;
  source_paths: Record<string, string | null | undefined>;
};

export type AgentTraceStep = {
  step_index: number;
  goal?: string | null;
  selected_action?: string | null;
  reason_summary?: string | null;
  evidence_refs: string[];
  alternatives?: string[];
  guard_result?: string | null;
  tool_action?: string | null;
  tool_result_status?: string | null;
  reflection_summary?: string | null;
  next_strategy_hint?: string | null;
  terminal_reason?: string | null;
  checkpoint_status?: string | null;
};

export type AgentTrace = {
  present: boolean;
  runtime?: string | null;
  goal: {
    task_id: string;
    cve_id: string;
    target_kernel: string;
    status?: string | null;
  };
  steps: AgentTraceStep[];
  trace_path?: string | null;
  checkpoint_path?: string | null;
  checkpoint_exists: boolean;
  resumed_from_checkpoint: boolean;
  terminal_reason?: string | null;
  raw_node_count?: number;
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
  evaluation_summary_path?: string | null;
  stage_routes: Record<string, unknown>;
  dispatch_modes: Record<string, unknown>;
  replay_files: string[];
  comparison: Record<string, unknown>;
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
  agent_decision_summary?: AgentDecisionSummary;
  agent_trace?: AgentTrace;
  agent_health?: AgentHealth;
  evaluation_summary?: Record<string, unknown> | null;
  reports: {
    json_path: string;
    md_path: string;
    evaluation_summary_path: string;
  };
  replay: ReplayPayload;
  process_summary?: ProcessSummary;
  stage_view?: StageViewNode[];
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
  force_new?: boolean;
  auto_run?: boolean;
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
  project_path: string;
  content: string;
  content_type: string;
  truncated: boolean;
  size?: number | null;
};
