export type OverviewMetricBlock = {
  total_tasks: number;
  running_tasks: number;
  success_tasks: number;
  failed_tasks: number;
  success_rate: number;
  build_backend: string;
  build_ready: boolean;
  validation_passed: number;
  validation_failed: number;
  latest_evaluation_summary?: string | null;
  delivery_ready: boolean;
  selected_model: string;
};

export type OverviewTask = {
  task_id: string;
  cve_id: string;
  target_kernel: string;
  status: string;
  current_attempt: number;
  max_attempts: number;
  updated_at: string;
};

export type FailureDistributionItem = {
  failure_type: string;
  total: number;
};

export type EvaluationSummaryItem = {
  fixture_name: string;
  total_fixtures: number;
  matched_fixtures: number;
  missing_fixtures: number;
  success_count: number;
  success_rate: number;
  average_attempts: number;
  failure_distribution: Record<string, number>;
  summary_json_path: string;
  summary_md_path: string;
  updated_at: string;
};

export type EventItem = {
  timestamp: string;
  kind: string;
  title: string;
  detail: string;
  task_id?: string;
};

export type LogTailBlock = {
  path: string;
  exists: boolean;
  lines: string[];
};

export type OverviewResponse = {
  metrics: OverviewMetricBlock;
  release: {
    submission_root: string;
    final_manifest_path?: string | null;
    final_gate_path?: string | null;
    final_gate_status?: string | null;
    evaluation_count: number;
    selected_models: {
      topology: string;
      primary_model: string;
      development_model: string;
      delivery_model: string;
      fallback_model: string;
      helper_models: Record<string, string>;
    };
  };
  evaluation_summaries: EvaluationSummaryItem[];
  recent_tasks: OverviewTask[];
  failure_distribution: FailureDistributionItem[];
  validation_distribution: Array<{
    status: string;
    total: number;
  }>;
  events: EventItem[];
  logs_tail: {
    system_log: LogTailBlock;
    jsonl_log?: LogTailBlock | null;
    latest_build_log?: LogTailBlock | null;
    paths: {
      system_log: string;
      jsonl_log?: string | null;
      latest_build_log?: string | null;
    };
  };
};
