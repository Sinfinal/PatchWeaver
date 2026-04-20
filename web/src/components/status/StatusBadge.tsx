import clsx from "clsx";

type StatusBadgeProps = {
  value?: string | null;
};

function mapStatusTheme(value?: string | null): string {
  const normalized = (value ?? "").toLowerCase();
  if (
    [
      "ok",
      "built",
      "success",
      "succeeded",
      "reported",
      "completed",
      "passed",
      "ready",
      "enabled",
      "healthy",
      "matched",
    ].includes(normalized)
  ) {
    return "success";
  }
  if (
    [
      "created",
      "analyzed",
      "running",
      "building",
      "validating",
      "reporting",
      "processing",
      "loading",
    ].includes(normalized)
  ) {
    return "running";
  }
  if (["warn", "partial", "pending", "queued", "skipped", "degraded"].includes(normalized)) {
    return "warn";
  }
  if (
    ["failed", "error", "danger", "disabled", "missing", "unsupported", "unreachable", "unmatched"].includes(
      normalized,
    )
  ) {
    return "danger";
  }
  return "idle";
}

function formatStatusLabel(value?: string | null): string {
  const normalized = (value ?? "").toLowerCase();
  const labelMap: Record<string, string> = {
    ok: "正常",
    built: "已构建",
    success: "成功",
    succeeded: "成功",
    reported: "已生成报告",
    completed: "已完成",
    passed: "已通过",
    ready: "就绪",
    enabled: "已启用",
    healthy: "健康",
    matched: "已匹配",
    created: "已创建",
    analyzed: "已分析",
    running: "运行中",
    building: "构建中",
    validating: "验证中",
    reporting: "生成报告中",
    processing: "处理中",
    loading: "加载中",
    warn: "警告",
    partial: "部分完成",
    pending: "待处理",
    queued: "排队中",
    skipped: "已跳过",
    degraded: "降级",
    failed: "失败",
    error: "错误",
    danger: "风险",
    disabled: "已禁用",
    missing: "缺失",
    unsupported: "不支持",
    unreachable: "不可达",
    unmatched: "未匹配",
    idle: "空闲",
    unknown: "未知",
  };
  return labelMap[normalized] ?? (value || "未知");
}

export function StatusBadge({ value }: StatusBadgeProps): JSX.Element {
  const theme = mapStatusTheme(value);
  return <span className={clsx("pw-status", theme)}>{formatStatusLabel(value)}</span>;
}
