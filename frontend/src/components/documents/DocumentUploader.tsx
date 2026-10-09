import * as React from "react";
import { UploadCloud } from "lucide-react";
import { getUploadLimits, uploadDocument } from "@/api/documents";
import { ApiError } from "@/api/client";
import type { DocumentUploadLimits, UploadResponse } from "@/types";
import { Button } from "@/components/ui/button";

interface DocumentUploaderProps {
  onUploaded: (result: UploadResponse) => void;
}

export default function DocumentUploader({ onUploaded }: DocumentUploaderProps) {
  const [limits, setLimits] = React.useState<DocumentUploadLimits | null>(null);
  const [dragOver, setDragOver] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    getUploadLimits()
      .then(setLimits)
      .catch(() => setLimits(null));
  }, []);

  async function handleFile(file: File) {
    setError(null);
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported.");
      return;
    }
    if (limits && file.size > limits.max_upload_size_mb * 1024 * 1024) {
      setError(`File exceeds the ${limits.max_upload_size_mb}MB upload limit.`);
      return;
    }
    setUploading(true);
    try {
      const result = await uploadDocument(file);
      onUploaded(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files?.[0];
          if (file) void handleFile(file);
        }}
        className={`flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors ${
          dragOver ? "border-primary bg-primary/5" : "border-border"
        }`}
      >
        <UploadCloud className="h-6 w-6 text-muted-foreground" />
        <p className="text-sm font-medium">Drag and drop a PDF here</p>
        <p className="text-xs text-muted-foreground">
          {limits ? `PDF only, up to ${limits.max_upload_size_mb}MB` : "PDF only"}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-1"
          disabled={uploading}
          onClick={() => inputRef.current?.click()}
        >
          {uploading ? "Uploading..." : "Choose file"}
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
            e.target.value = "";
          }}
        />
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
