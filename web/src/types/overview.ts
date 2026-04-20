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
  recent_tasks: OverviewTask[];
  failure_distribution: FailureDistributionItem[];
  validation_distribution: Array<{
    status: string;
    total: number;
  }>;
  events: EventItem[];
  logs_tail: {
    system_log: LogTailBlock;
    latest_build_log?: LogTailBlock | null;
    paths: {
      system_log: string;
      latest_build_log?: string | null;
    };
  };
};
