import type { MachineProfile } from "./tasks";

export type DoctorCheck = {
  category: string;
  name: string;
  label: string;
  ok: boolean;
  status: string;
  detail: string;
};

export type DoctorReport = {
  generated_at: string;
  runtime: {
    project_root: string;
    workspace_root: string;
    database_path: string;
    manifest_dir: string;
    configured_default_kernel: string;
    detected_target_kernel?: string | null;
    detected_target_kernel_source?: string | null;
    machine_kernel?: string | null;
    machine_arch?: string | null;
    max_attempts: number;
    python_version: string;
    skill_source_priority?: string[];
  };
  machine_profile?: MachineProfile | null;
  build_env: Record<string, unknown>;
  checks: DoctorCheck[];
  summary: {
    total: number;
    ok: number;
    warn: number;
    error: number;
  };
};

export type DoctorRepairAction = {
  name: string;
  label: string;
  status: string;
  detail: string;
  path?: string | null;
  executed?: boolean;
  stdout_excerpt?: string;
  stderr_excerpt?: string;
};

export type DoctorRepairResult = {
  started_at: string;
  finished_at: string;
  status: string;
  summary: {
    before: DoctorReport["summary"];
    after: DoctorReport["summary"];
    remaining_error_count: number;
  };
  actions: DoctorRepairAction[];
  remaining_errors: DoctorCheck[];
  script: {
    path: string | null;
    content: string;
    auto_execute_enabled: boolean;
    host_repair_executed: boolean;
  };
  report: DoctorReport;
};
