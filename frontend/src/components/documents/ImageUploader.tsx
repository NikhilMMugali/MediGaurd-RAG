import * as React from "react";
import { ImagePlus, Trash2 } from "lucide-react";
import { getUploadLimits, uploadImage } from "@/api/documents";
import { listAllPatientIds } from "@/api/patients";
import { ApiError } from "@/api/client";
import type { ImageUploadResponse } from "@/types";
import { Button } from "@/components/ui/button";

export const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
const ACCEPTED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];

export function validateImageFile(file: File, maxMb: number | null): string | null {
  const lower = file.name.toLowerCase();
  const okType = ACCEPTED_IMAGE_TYPES.includes(file.type) || ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
  if (!okType) return "Only JPG, PNG, and WEBP images are supported.";
  if (file.size === 0) return "This file is empty.";
  if (maxMb !== null && file.size > maxMb * 1024 * 1024) return `File exceeds the ${maxMb}MB upload limit.`;
  return null;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface ImageUploaderProps {
  onUploaded: (result: ImageUploadResponse, file: File) => void;
  // Increment to clear the current selection (e.g. after "upload another").
  resetKey?: number;
}

export default function ImageUploader({ onUploaded, resetKey = 0 }: ImageUploaderProps) {
  const [maxMb, setMaxMb] = React.useState<number | null>(null);
  const [file, setFile] = React.useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null);
  const [patients, setPatients] = React.useState<string[]>([]);
  const [patientId, setPatientId] = React.useState("");
  const [dragOver, setDragOver] = React.useState(false);
  const [progress, setProgress] = React.useState<number | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const uploading = progress !== null;

  React.useEffect(() => {
    getUploadLimits()
      .then((limits) => setMaxMb(limits.max_upload_size_mb))
      .catch(() => setMaxMb(null));
    listAllPatientIds()
      .then(setPatients)
      .catch(() => setPatients([]));
  }, []);

  React.useEffect(() => {
    setFile(null);
    setError(null);
    setProgress(null);
  }, [resetKey]);

  // The preview is an object URL for the chosen file; release it when the
  // selection changes or the component goes away.
  React.useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function choose(next: File | undefined) {
    if (!next) return;
    const problem = validateImageFile(next, maxMb);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setFile(next);
  }

  async function submit() {
    if (!file || uploading) return;
    setError(null);
    setProgress(0);
    try {
      const result = await uploadImage(file, patientId || null, setProgress);
      onUploaded(result, file);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed. Please try again.");
    } finally {
      setProgress(null);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {!file ? (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            choose(e.dataTransfer.files?.[0]);
          }}
          className={`flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors ${
            dragOver ? "border-primary bg-primary/5" : "border-border"
          }`}
        >
          <ImagePlus className="h-6 w-6 text-muted-foreground" />
          <p className="text-sm font-medium">Drag and drop an image here</p>
          <p className="text-xs text-muted-foreground">
            JPG, PNG or WEBP{maxMb ? `, up to ${maxMb}MB` : ""}. A flat, well-lit photo or scan works best.
          </p>
          <Button type="button" variant="outline" size="sm" className="mt-1" onClick={() => inputRef.current?.click()}>
            Choose image
          </Button>
        </div>
      ) : (
        <div className="flex gap-3 rounded-lg border bg-card p-3">
          {previewUrl && (
            <img src={previewUrl} alt={`Preview of ${file.name}`} className="h-28 w-28 shrink-0 rounded border object-cover" />
          )}
          <div className="flex min-w-0 flex-1 flex-col gap-1.5 text-sm">
            <p className="truncate font-medium">{file.name}</p>
            <p className="text-xs text-muted-foreground">{formatFileSize(file.size)}</p>
            <div className="mt-auto flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" disabled={uploading} onClick={() => inputRef.current?.click()}>
                Replace
              </Button>
              <Button type="button" variant="ghost" size="sm" disabled={uploading} onClick={() => setFile(null)}>
                <Trash2 className="mr-1 h-3.5 w-3.5" />
                Remove
              </Button>
            </div>
          </div>
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_IMAGE_TYPES.join(",")}
        className="hidden"
        aria-label="Choose an image to upload"
        onChange={(e) => {
          choose(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      <div className="flex flex-col gap-1">
        <label htmlFor="ocr-patient" className="text-xs font-medium text-muted-foreground">
          Patient (optional)
        </label>
        <select
          id="ocr-patient"
          value={patientId}
          disabled={uploading}
          onChange={(e) => setPatientId(e.target.value)}
          className="h-9 rounded-md border bg-background px-2 text-sm"
        >
          <option value="">Identify from the image (recommended)</option>
          {patients.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </select>
        <p className="text-[11px] text-muted-foreground">
          Choosing a patient files the image under them. If the name printed on it clearly differs, you will be asked to confirm.
        </p>
      </div>

      {uploading && (
        <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((progress ?? 0) * 100)} className="flex flex-col gap-1">
          <div className="h-1.5 w-full overflow-hidden rounded bg-muted">
            <div className="h-full bg-primary transition-all" style={{ width: `${Math.round((progress ?? 0) * 100)}%` }} />
          </div>
          <p className="text-xs text-muted-foreground">Uploading {Math.round((progress ?? 0) * 100)}%</p>
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <Button type="button" disabled={!file || uploading} onClick={() => void submit()}>
        {uploading ? "Uploading..." : "Upload and read text"}
      </Button>
    </div>
  );
}
