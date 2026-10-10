import { apiRequest } from "@/api/client";
import type { PatientListResponse, PatientStatusResponse } from "@/types";

export function listPatients(limit = 20, offset = 0) {
  return apiRequest<PatientListResponse>(`/api/patients?limit=${limit}&offset=${offset}`);
}

export function getPatientStatus(patientId: string) {
  return apiRequest<PatientStatusResponse>(`/api/patients/${encodeURIComponent(patientId)}/status`);
}

// The list endpoint caps `limit` at 100 (a larger value is a 422), and an admin
// can see more patients than that — so walk the pages. Bounded so a server that
// misreports `total` can never loop forever.
export async function listAllPatientIds(): Promise<string[]> {
  const ids: string[] = [];
  for (let page = 0; page < 50; page++) {
    const res = await listPatients(100, ids.length);
    ids.push(...res.patient_ids);
    if (res.patient_ids.length === 0 || ids.length >= res.total) break;
  }
  return ids;
}
