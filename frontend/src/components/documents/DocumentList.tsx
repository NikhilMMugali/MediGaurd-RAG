import * as React from "react";
import { FileText, Image as ImageIcon, RefreshCw, Search } from "lucide-react";
import { listDocuments } from "@/api/documents";
import { ApiError } from "@/api/client";
import type { DocumentListItem } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingState } from "@/components/common/StateViews";

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

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

interface DocumentListProps {
  selectedId: string | null;
  onSelect: (doc: DocumentListItem) => void;
  refreshKey: number;
}

export default function DocumentList({ selectedId, onSelect, refreshKey }: DocumentListProps) {
  const [documents, setDocuments] = React.useState<DocumentListItem[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");

  const load = React.useCallback(() => {
    setError(null);
    listDocuments()
      .then((res) => setDocuments(res.documents))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load documents."));
  }, []);

  React.useEffect(() => {
    load();
  }, [load, refreshKey]);

  const filtered = (documents ?? []).filter((d) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return d.file_name.toLowerCase().includes(q) || (d.patient_id ?? "").toLowerCase().includes(q);
  });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by filename or patient id..."
            className="pl-8"
          />
        </div>
        <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={load} aria-label="Refresh documents">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {documents === null && !error && <LoadingState label="Loading documents..." />}
      {error && <ErrorState message={error} onRetry={load} />}
      {documents !== null && !error && filtered.length === 0 && (
        <EmptyState icon={FileText} title="No documents yet" description="Upload a PDF or an image above to get started." />
      )}

      <div className="flex flex-col gap-1.5">
        {filtered.map((doc) => (
          <button
            key={doc.document_id}
            type="button"
            onClick={() => onSelect(doc)}
            className={`flex flex-col gap-1 rounded-md border px-3 py-2 text-left text-sm transition-colors ${
              selectedId === doc.document_id ? "border-primary bg-primary/5" : "hover:bg-accent"
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1.5 font-medium">
                {doc.source_type === "OCR_IMAGE" ? (
                  <ImageIcon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-label="Image (OCR)" />
                ) : (
                  <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-label="PDF" />
                )}
                <span className="truncate">{doc.file_name}</span>
              </span>
              <Badge variant={STATUS_VARIANT[doc.status] ?? "muted"} className="shrink-0">
                {doc.status.replace(/_/g, " ")}
              </Badge>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {doc.patient_id && <span>{doc.patient_id}</span>}
              {doc.uploaded_by && <span>· {doc.uploaded_by}</span>}
              <span>· {formatDate(doc.created_at)}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
