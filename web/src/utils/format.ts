import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";

dayjs.extend(utc);

const SQLITE_UTC_PATTERN = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?$/;

function parseTime(value: string) {
  if (SQLITE_UTC_PATTERN.test(value)) {
    return dayjs.utc(`${value.replace(" ", "T")}Z`);
  }

  return dayjs(value);
}

export function formatTime(value?: string | null): string {
  if (!value) {
    return "未记录";
  }

  const parsed = parseTime(value);
  if (!parsed.isValid()) {
    return value;
  }

  return parsed.local().format("YYYY-MM-DD HH:mm:ss");
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
