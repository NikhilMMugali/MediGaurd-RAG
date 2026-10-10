import { apiRequest, apiRequestBlob, apiUploadWithProgress } from "@/api/client";
import type {
  DocumentListResponse,
  DocumentQueryResponse,
  DocumentStatusResponse,
  DocumentUploadLimits,
  ImageUploadResponse,
  OcrResponse,
  UploadResponse,
} from "@/types";

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

export function getDocumentFileBlob(documentId: string) {
  return apiRequestBlob(`/api/documents/${encodeURIComponent(documentId)}/file`);
}

export function uploadImage(file: File, patientId: string | null, onProgress: (fraction: number) => void) {
  const formData = new FormData();
  formData.append("file", file);
  if (patientId) formData.append("patient_id", patientId);
  return apiUploadWithProgress<ImageUploadResponse>("/api/documents/upload-image", formData, onProgress);
}

export function getDocumentOcr(documentId: string) {
  return apiRequest<OcrResponse>(`/api/documents/${encodeURIComponent(documentId)}/ocr`);
}

export function confirmImagePatient(documentId: string, patientId: string) {
  return apiRequest<ImageUploadResponse>(`/api/documents/${encodeURIComponent(documentId)}/confirm-patient`, {
    method: "POST",
    body: { patient_id: patientId },
  });
}
