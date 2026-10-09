import { apiRequest } from "@/api/client";
import type { DocumentListResponse, DocumentQueryResponse, DocumentStatusResponse, DocumentUploadLimits, UploadResponse } from "@/types";

export function getUploadLimits() {
  return apiRequest<DocumentUploadLimits>("/api/documents/limits");
}

export function uploadDocument(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<UploadResponse>("/api/documents/upload", {
    method: "POST",
    formData,
  });
}

export function listDocuments() {
  return apiRequest<DocumentListResponse>("/api/documents");
}

export function getDocumentStatus(documentId: string) {
  return apiRequest<DocumentStatusResponse>(`/api/documents/${encodeURIComponent(documentId)}/status`);
}

export function queryDocument(documentId: string, question: string) {
  return apiRequest<DocumentQueryResponse>("/api/documents/query", {
    method: "POST",
    body: { document_id: documentId, question },
  });
}
