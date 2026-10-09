import * as React from "react";
import { ShieldAlert } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { CAN_VIEW_DOCUMENTS } from "@/lib/roles";
import type { DocumentListItem, UploadResponse } from "@/types";
import DocumentUploader from "@/components/documents/DocumentUploader";
import DocumentProcessingStatus from "@/components/documents/DocumentProcessingStatus";
import DocumentList from "@/components/documents/DocumentList";
import DocumentQuestionPanel from "@/components/documents/DocumentQuestionPanel";
import { EmptyState } from "@/components/common/StateViews";

export default function DocumentIntelligence() {
  const { user } = useAuth();
  const [refreshKey, setRefreshKey] = React.useState(0);
  const [lastUploadedId, setLastUploadedId] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<DocumentListItem | null>(null);

  if (!user) return null;

  if (!CAN_VIEW_DOCUMENTS.includes(user.role)) {
    return (
      <div className="p-6">
        <EmptyState
          icon={ShieldAlert}
          title="Document Intelligence is not available for your role"
          description="Document upload and review is limited to clinical and administrative roles."
        />
      </div>
    );
  }

  function handleUploaded(result: UploadResponse) {
    setLastUploadedId(result.document_id);
    setRefreshKey((k) => k + 1);
  }

  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-6">
      <div>
        <h1 className="text-lg font-semibold">Document Intelligence</h1>
        <p className="text-sm text-muted-foreground">Upload patient PDFs, track processing, and ask questions grounded in their content.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <DocumentUploader onUploaded={handleUploaded} />
        {lastUploadedId && <DocumentProcessingStatus documentId={lastUploadedId} />}
      </div>

      <div className="grid min-h-0 flex-1 gap-5 lg:grid-cols-2">
        <div className="flex min-h-0 flex-col overflow-y-auto rounded-lg border bg-card p-4">
          <p className="mb-2 text-sm font-semibold">Available documents</p>
          <DocumentList
            selectedId={selected?.document_id ?? null}
            onSelect={setSelected}
            refreshKey={refreshKey}
          />
        </div>

        <div className="flex min-h-0 flex-col rounded-lg border bg-card p-4">
          <p className="mb-2 text-sm font-semibold">Ask about documents</p>
          <DocumentQuestionPanel documentId={selected?.document_id ?? null} documentName={selected?.file_name ?? null} />
        </div>
      </div>
    </div>
  );
}
