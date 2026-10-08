export type Role = "DOCTOR" | "NURSE" | "FINANCE" | "RECEPTION" | "ADMIN";

export interface AuthUser {
  username: string;
  full_name: string;
  role: Role;
  department: string | null;
}

export interface LoginResponse extends AuthUser {
  access_token: string;
  token_type: string;
}

export interface Citation {
  source_id: string;
  source_type: string;
  record_id: string | null;
  file_name: string | null;
  page: number | null;
  section: string | null;
  date: string | null;
  patient_id: string | null;
}

export type RagStatus = "ANSWERED" | "DENIED" | "NO_AUTHORIZED_CONTEXT";

export interface RagQueryResponse {
  answer: string;
  status: RagStatus;
  citations: Citation[];
  retrieved_count: number;
  debug: Record<string, unknown> | null;
}

export interface PatientListResponse {
  patient_ids: string[];
  total: number;
  scope: "assigned" | "all";
}

export type PatientStatusLabel = "Stable" | "Attention" | "No Recent Information";

export interface PatientStatusResponse {
  patient_id: string;
  status: PatientStatusLabel;
  summary: string;
  citations: Citation[];
}

export interface UploadResponse {
  document_id: string;
  file_name: string;
  status: string;
  page_count: number;
  message: string;
  patient_id: string | null;
  records_created: number;
  chunks_indexed: number;
}

export interface DatabaseStats {
  patients: number;
  encounters: number;
  conditions: number;
  medications: number;
  observations: number;
  allergies: number;
  procedures: number;
  claims: number;
  claims_transactions: number;
  knowledge_records: number;
  documents: number;
  vectors: number;
}

export interface RecentUpload {
  file_name: string;
  status: string;
  created_at: string;
  patient_id: string | null;
}

export interface RecentSecurityEvent {
  status: string;
  role: string | null;
  timestamp: string;
  reason: string | null;
}

export interface RecentActivity {
  recent_uploads: RecentUpload[];
  recent_security_events: RecentSecurityEvent[];
}
