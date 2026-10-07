import { apiRequest } from "@/api/client";
import type { PatientListResponse, PatientStatusResponse } from "@/types";

export function listPatients(limit = 20, offset = 0) {
  return apiRequest<PatientListResponse>(`/api/patients?limit=${limit}&offset=${offset}`);
}

export function getPatientStatus(patientId: string) {
  return apiRequest<PatientStatusResponse>(`/api/patients/${encodeURIComponent(patientId)}/status`);
}
