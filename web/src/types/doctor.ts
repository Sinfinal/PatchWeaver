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
    default_kernel: string;
    max_attempts: number;
    python_version: string;
  };
  build_env: Record<string, unknown>;
  checks: DoctorCheck[];
  summary: {
    total: number;
    ok: number;
    warn: number;
    error: number;
  };
};
