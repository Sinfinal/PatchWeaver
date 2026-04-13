import clsx from "clsx";

type StatusBadgeProps = {
  value?: string | null;
};

function mapStatus(value?: string | null): string {
  const normalized = (value ?? "").toLowerCase();
  if (["ok", "built", "success", "succeeded", "reported", "completed"].includes(normalized)) {
    return "success";
  }
  if (["created", "analyzed", "running", "building", "validating"].includes(normalized)) {
    return "running";
  }
  if (["warn", "partial", "pending"].includes(normalized)) {
    return "warn";
  }
  if (["failed", "error", "danger"].includes(normalized)) {
    return "danger";
  }
  return "idle";
}

export function StatusBadge({ value }: StatusBadgeProps): JSX.Element {
  const theme = mapStatus(value);
  return <span className={clsx("pw-status", theme)}>{value ?? "unknown"}</span>;
}
