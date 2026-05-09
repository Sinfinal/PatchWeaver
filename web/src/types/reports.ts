import type { AgentDecisionSummary, ReplayPayload, TaskSummary } from "./tasks";

export type EvaluationGroupItem = {
  fixture_group: string;
  group_id?: string;
  display_name: string;
  summary_json_path: string;
  summary_md_path: string;
  total_fixtures: number;
  matched_fixtures: number;
  missing_fixtures: number;
  success_count: number;
  success_rate: number;
  average_attempts: number;
  updated_at: string;
};

export type EvaluationGroupListResponse = {
  items: EvaluationGroupItem[];
};

export type EvaluationFixtureSummary = {
  fixture_id: string;
  cve_id?: string | null;
  target_kernel?: string | null;
  matched?: boolean;
  task_id?: string | null;
  final_status?: string | null;
  attempts?: number | null;
  latest_failure_type?: string | null;
  evaluation_summary_path?: string | null;
  report_route?: string | null;
  task_report_route?: string | null;
  task_detail_route?: string | null;
};

export type EvaluationGroupSummaryResponse = {
  fixture_group: string;
  group_id?: string;
  display_name: string;
  summary_json_path: string;
  summary_md_path: string;
  summary_markdown?: string | null;
  summary: {
    fixture_name: string;
    total_fixtures: number;
    matched_fixtures: number;
    missing_fixtures: number;
    success_count: number;
    success_rate: number;
    average_attempts: number;
    failure_distribution: Record<string, number>;
    fixtures?: EvaluationFixtureSummary[];
  };
  fixtures: EvaluationFixtureSummary[];
};

export type EvaluationFixtureDetailResponse = {
  fixture_group: string;
  group_id?: string;
  display_name: string;
  fixture_id: string;
  detail_path: string;
  detail: {
    fixture_id?: string;
    task_id?: string | null;
    cve_id?: string | null;
    target_kernel?: string | null;
    task_status?: string | null;
    task_summary?: Record<string, unknown> | null;
    replay_comparison?: Record<string, unknown> | null;
  } & Record<string, unknown>;
  task_report_route?: string | null;
  task_detail_route?: string | null;
};

export type TaskReportResponse = {
  task: TaskSummary;
  report: {
    json_path: string;
    md_path: string;
    json?: Record<string, unknown> | null;
    markdown?: string | null;
  };
  agent_decision_summary?: AgentDecisionSummary;
  latest_failure?: Record<string, unknown> | null;
  latest_validation?: Record<string, unknown> | null;
  evaluation_summary?: Record<string, unknown> | null;
  replay: ReplayPayload;
  artifact_index: Array<{
    artifact_type: string;
    artifact_path: string;
    relative_path: string;
    summary: string;
  }>;
  result_source: {
    report_json_exists: boolean;
    report_md_exists: boolean;
    evaluation_summary_exists: boolean;
  };
};
