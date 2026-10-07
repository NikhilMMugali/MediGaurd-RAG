import { apiRequest } from "@/api/client";
import type { UploadResponse } from "@/types";

export function uploadDocument(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<UploadResponse>("/api/documents/upload", {
    method: "POST",
    formData,
  });
}
