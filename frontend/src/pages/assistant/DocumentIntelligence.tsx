import * as React from "react";
import { FileText, Image as ImageIcon, ShieldAlert } from "lucide-react";
import { useAuth } from "@/auth/AuthContext";
import { CAN_VIEW_DOCUMENTS } from "@/lib/roles";
import { uploadImage } from "@/api/documents";
import type { Citation, DocumentListItem, DocumentStatusResponse, ImageUploadResponse, UploadResponse } from "@/types";
import DocumentUploader from "@/components/documents/DocumentUploader";
import DocumentProcessingStatus from "@/components/documents/DocumentProcessingStatus";
import ImageUploader from "@/components/documents/ImageUploader";
import ImageProcessingStatus from "@/components/documents/ImageProcessingStatus";
import DocumentList from "@/components/documents/DocumentList";
import DocumentQuestionPanel from "@/components/documents/DocumentQuestionPanel";
import SourceViewerPanel from "@/components/documents/SourceViewerPanel";
import { EmptyState } from "@/components/common/StateViews";

type UploadTab = "pdf" | "image";

const TABS: { id: UploadTab; label: string; icon: typeof FileText }[] = [
  { id: "pdf", label: "PDF Upload", icon: FileText },
  { id: "image", label: "Upload Image using OCR", icon: ImageIcon },
];

export default function DocumentIntelligence() {
  const { user } = useAuth();
  const [tab, setTab] = React.useState<UploadTab>("pdf");
  const [refreshKey, setRefreshKey] = React.useState(0);
  const [lastUploadedId, setLastUploadedId] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<DocumentListItem | null>(null);
  const [activeCitation, setActiveCitation] = React.useState<Citation | null>(null);
  const [imageJob, setImageJob] = React.useState<{ documentId: string; file: File; attempt: number } | null>(null);
  const [imageResetKey, setImageResetKey] = React.useState(0);
  const questionRef = React.useRef<HTMLDivElement>(null);

  // A source opened for one document must not linger when another is chosen.
  React.useEffect(() => {
    setActiveCitation(null);
  }, [selected?.document_id]);

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

  function handlePdfUploaded(result: UploadResponse) {
    setLastUploadedId(result.document_id);
    setRefreshKey((k) => k + 1);
  }

  function handleImageUploaded(result: ImageUploadResponse, file: File) {
    setImageJob((prev) => ({ documentId: result.document_id, file, attempt: (prev?.attempt ?? 0) + 1 }));
    setRefreshKey((k) => k + 1);
  }

  async function retryImage() {
    if (!imageJob) return;
    try {
      const result = await uploadImage(imageJob.file, null, () => {});
      handleImageUploaded(result, imageJob.file);
    } catch {
      // The status panel keeps showing the failure; the user can retry again.
    }
  }

  function askAboutImage(status: DocumentStatusResponse) {
    setSelected({
      document_id: status.document_id,
      file_name: status.file_name,
      status: status.status,
      document_type: "image",
      patient_id: status.patient_id,
      uploaded_by: status.uploaded_by,
      created_at: status.created_at,
      source_type: status.source_type,
    });
    questionRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-6">
      <div>
        <h1 className="text-lg font-semibold">Document Intelligence</h1>
        <p className="text-sm text-muted-foreground">
          Upload patient PDFs or images, track processing, and ask questions grounded in their content.
        </p>
      </div>

      <div className="flex flex-col gap-4 rounded-lg border bg-card p-4">
        <div role="tablist" aria-label="Upload type" className="flex gap-1 rounded-md bg-muted p-1 sm:w-fit">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              role="tab"
              type="button"
              id={`tab-${id}`}
              aria-selected={tab === id}
              aria-controls={`panel-${id}`}
              onClick={() => setTab(id)}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium transition-colors sm:flex-none ${
                tab === id ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>

        {/* Both panels stay mounted so switching tabs never loses an upload in progress. */}
        <div role="tabpanel" id="panel-pdf" aria-labelledby="tab-pdf" className={`gap-4 lg:grid-cols-[minmax(0,1fr)_320px] ${tab === "pdf" ? "grid" : "hidden"}`}>
          <div className="flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">
              Upload a PDF report. Its text is extracted directly from the file (not OCR) and made searchable.
            </p>
            <DocumentUploader onUploaded={handlePdfUploaded} />
          </div>
          {lastUploadedId && <DocumentProcessingStatus documentId={lastUploadedId} />}
        </div>

        <div role="tabpanel" id="panel-image" aria-labelledby="tab-image" className={`gap-4 lg:grid-cols-[minmax(0,1fr)_360px] ${tab === "image" ? "grid" : "hidden"}`}>
          <div className="flex flex-col gap-2">
            <h2 className="text-sm font-semibold">Upload Image using OCR</h2>
            <p className="text-xs text-muted-foreground">
              Upload an image of a patient report or hospital document. MediGaurd extracts the visible text and makes it searchable through the secure AI assistant.
            </p>
            <ImageUploader onUploaded={handleImageUploaded} resetKey={imageResetKey} />
          </div>
          {imageJob && (
            <div className="flex flex-col gap-2">
              <ImageProcessingStatus
                key={`${imageJob.documentId}:${imageJob.attempt}`}
                documentId={imageJob.documentId}
                onAsk={askAboutImage}
                onRetry={() => void retryImage()}
              />
              <button
                type="button"
                className="self-start text-xs text-muted-foreground underline"
                onClick={() => {
                  setImageJob(null);
                  setImageResetKey((k) => k + 1);
                }}
              >
                Upload another image
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-5 lg:grid-cols-2">
        <div className="flex min-h-0 flex-col overflow-y-auto rounded-lg border bg-card p-4">
          <p className="mb-2 text-sm font-semibold">Available documents</p>
          <DocumentList selectedId={selected?.document_id ?? null} onSelect={setSelected} refreshKey={refreshKey} />
        </div>

        <div ref={questionRef} className="flex min-h-0 flex-col rounded-lg border bg-card p-4">
          <p className="mb-2 text-sm font-semibold">Ask about documents</p>
          <DocumentQuestionPanel
            documentId={selected?.document_id ?? null}
            documentName={selected?.file_name ?? null}
            isImage={selected?.source_type === "OCR_IMAGE"}
            onCitationClick={setActiveCitation}
          />
        </div>
      </div>

      {activeCitation && (
        <div className="fixed inset-y-0 right-0 z-50 w-full bg-background shadow-2xl md:w-[460px]">
          <SourceViewerPanel citation={activeCitation} onClose={() => setActiveCitation(null)} />
        </div>
      )}
    </div>
  );
}
