import { apiGet, apiPost } from "./http";
import type { DoctorRepairResult, DoctorReport } from "../types/doctor";

export function fetchDoctor(): Promise<DoctorReport> {
  return apiGet<DoctorReport>("/doctor");
}

export function runDoctor(): Promise<DoctorReport> {
  return apiPost<DoctorReport>("/doctor/run");
}

export function repairDoctor(): Promise<DoctorRepairResult> {
  return apiPost<DoctorRepairResult>("/doctor/repair");
}
