import { apiRequest } from "@/api/client";
import type { RagQueryResponse } from "@/types";

export function queryRag(question: string, patientId?: string | null) {
  return apiRequest<RagQueryResponse>("/api/rag/query", {
    method: "POST",
    body: { question, patient_id: patientId ?? null },
  });
}
