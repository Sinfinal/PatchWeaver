import dayjs from "dayjs";

export function formatTime(value?: string | null): string {
  if (!value) {
    return "未记录";
  }
  return dayjs(value).format("YYYY-MM-DD HH:mm:ss");
}

export function formatCount(value?: number | null): string {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${value}`;
}

export function formatPercent(value?: number | null, digits = 2): string {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${(value * 100).toFixed(digits)}%`;
}

export function shortenPath(value?: string | null): string {
  if (!value) {
    return "-";
  }
  return value.replace(/\\/g, "/");
}

export function toFixtureGroupPath(value: string): string {
  return value.trim().toLowerCase().replace(/_/g, "-");
}

export function copyText(value: string): Promise<void> {
  return navigator.clipboard.writeText(value);
}
