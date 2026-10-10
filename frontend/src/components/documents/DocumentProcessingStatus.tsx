import * as React from "react";
import { getDocumentStatus } from "@/api/documents";
import type { DocumentStatusResponse } from "@/types";
import { Badge } from "@/components/ui/badge";
import { LoadingState } from "@/components/common/StateViews";

type BadgeVariant = "success" | "warning" | "destructive" | "secondary" | "muted";

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  COMPLETED: "success",
  NEEDS_REVIEW: "warning",
  FAILED: "destructive",
  RECEIVED: "secondary",
  EXTRACTING: "secondary",
  MAPPING: "secondary",
  CHUNKING: "secondary",
  VALIDATING: "secondary",
  OCR_PROCESSING: "secondary",
  IDENTIFYING_PATIENT: "secondary",
  INDEXING: "secondary",
};

interface DocumentProcessingStatusProps {
  documentId: string;
}

// Fetches the persisted, authoritative record from the database rather than
// trusting the upload response alone — real processing status, not an
// optimistic client-side guess (section B "Processing Status").
export default function DocumentProcessingStatus({ documentId }: DocumentProcessingStatusProps) {
  const [data, setData] = React.useState<DocumentStatusResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setData(null);
    setError(null);
    getDocumentStatus(documentId)
      .then(setData)
      .catch(() => setError("Could not load processing status."));
  }, [documentId]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!data) return <LoadingState label="Checking status..." />;

  return (
    <div className="flex flex-col gap-2 rounded-lg border bg-card p-3 text-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-medium">{data.file_name}</span>
        <Badge variant={STATUS_VARIANT[data.status] ?? "muted"}>{data.status.replace(/_/g, " ")}</Badge>
      </div>
      <dl className="grid grid-cols-2 gap-y-1 text-xs text-muted-foreground">
        {data.patient_id && (
          <>
            <dt>Patient</dt>
            <dd className="text-foreground">{data.patient_id}</dd>
          </>
        )}
        {data.page_count !== null && (
          <>
            <dt>Pages</dt>
            <dd className="text-foreground">{data.page_count}</dd>
          </>
        )}
        <dt>Records created</dt>
        <dd className="text-foreground">{data.records_created}</dd>
        <dt>Chunks indexed</dt>
        <dd className="text-foreground">{data.chunks_created}</dd>
        <dt>Uploaded by</dt>
        <dd className="text-foreground">{data.uploaded_by ?? "—"}</dd>
      </dl>
      {data.error_message && <p className="text-xs text-amber-700">{data.error_message}</p>}
    </div>
  );
}
