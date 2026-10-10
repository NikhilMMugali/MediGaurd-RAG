import * as React from "react";
import { CheckCircle2, Circle, Loader2, TriangleAlert, XCircle } from "lucide-react";
import { confirmImagePatient, getDocumentOcr, getDocumentStatus } from "@/api/documents";
import { listAllPatientIds } from "@/api/patients";
import { ApiError } from "@/api/client";
import type { DocumentStatusResponse, OcrResponse } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const TERMINAL = new Set(["COMPLETED", "NEEDS_REVIEW", "FAILED"]);

// The server's real stages, in order. Position in this list is derived from
// the persisted status — nothing here advances on a timer.
const STAGES: { status: string; label: string }[] = [
  { status: "RECEIVED", label: "Uploaded" },
  { status: "VALIDATING", label: "Validating" },
  { status: "OCR_PROCESSING", label: "Reading text (OCR)" },
  { status: "IDENTIFYING_PATIENT", label: "Identifying patient" },
  { status: "MAPPING", label: "Preparing records" },
  { status: "INDEXING", label: "Indexing for search" },
];

const PREVIEW_CHARS = 500;

interface ImageProcessingStatusProps {
  documentId: string;
  onAsk: (status: DocumentStatusResponse) => void;
  // Re-submits the same image (offered after a failure).
  onRetry?: () => void;
}

export default function ImageProcessingStatus({ documentId, onAsk, onRetry }: ImageProcessingStatusProps) {
  const [data, setData] = React.useState<DocumentStatusResponse | null>(null);
  const [ocr, setOcr] = React.useState<OcrResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [pollKey, setPollKey] = React.useState(0);
  const [showFullText, setShowFullText] = React.useState(false);
  const [patients, setPatients] = React.useState<string[]>([]);
  const [confirmPatient, setConfirmPatient] = React.useState("");
  const [confirming, setConfirming] = React.useState(false);
  const [confirmError, setConfirmError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    setData(null);
    setOcr(null);
    setError(null);
    setShowFullText(false);

    const tick = async () => {
      try {
        const status = await getDocumentStatus(documentId);
        if (cancelled) return;
        failures = 0;
        setData(status);
        if (!TERMINAL.has(status.status)) timer = setTimeout(tick, 1500);
      } catch {
        if (cancelled) return;
        failures += 1;
        if (failures >= 3) setError("Could not load processing status.");
        else timer = setTimeout(tick, 2000);
      }
    };
    void tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [documentId, pollKey]);

  const finished = data !== null && TERMINAL.has(data.status);
  const hasOcr = finished && data.ocr_quality !== null;

  React.useEffect(() => {
    if (!hasOcr) return;
    let cancelled = false;
    getDocumentOcr(documentId)
      .then((result) => {
        if (!cancelled) setOcr(result);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [hasOcr, documentId]);

  const needsPatientConfirmation = data?.status === "NEEDS_REVIEW" && data.ocr_quality !== "poor";
  React.useEffect(() => {
    if (!needsPatientConfirmation) return;
    listAllPatientIds()
      .then(setPatients)
      .catch(() => setPatients([]));
  }, [needsPatientConfirmation]);

  async function confirm() {
    if (!confirmPatient) return;
    setConfirming(true);
    setConfirmError(null);
    try {
      await confirmImagePatient(documentId, confirmPatient);
      setPollKey((k) => k + 1); // resume polling the same document
    } catch (err) {
      setConfirmError(err instanceof ApiError ? err.message : "Could not confirm the patient. Please try again.");
    } finally {
      setConfirming(false);
    }
  }

  if (error) {
    return (
      <div className="flex flex-col gap-2 rounded-lg border bg-card p-3 text-sm">
        <p className="text-destructive">{error}</p>
        <Button size="sm" variant="outline" className="self-start" onClick={() => setPollKey((k) => k + 1)}>
          Retry
        </Button>
      </div>
    );
  }
  if (!data) {
    return (
      <p className="flex items-center gap-1.5 rounded-lg border bg-card p-3 text-sm text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Checking status...
      </p>
    );
  }

  const currentIndex = STAGES.findIndex((s) => s.status === data.status);
  const ready = data.status === "COMPLETED";
  const text = ocr?.text ?? "";
  const previewText = showFullText ? text : text.slice(0, PREVIEW_CHARS);

  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-card p-3 text-sm" data-testid="image-processing-status">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-medium">{data.file_name}</span>
        <Badge variant={ready ? "success" : data.status === "FAILED" ? "destructive" : data.status === "NEEDS_REVIEW" ? "warning" : "secondary"}>
          {ready ? "Ready" : data.status.replace(/_/g, " ")}
        </Badge>
      </div>

      {!finished && (
        <ol className="flex flex-col gap-1" aria-label="Processing stages">
          {STAGES.map((stage, index) => {
            const done = currentIndex > index;
            const current = currentIndex === index;
            return (
              <li key={stage.status} className={`flex items-center gap-2 text-xs ${current ? "font-medium text-foreground" : "text-muted-foreground"}`}>
                {done ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                ) : current ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Circle className="h-3.5 w-3.5" />
                )}
                {stage.label}
              </li>
            );
          })}
        </ol>
      )}

      {ready && (
        <p className="flex items-center gap-1.5 text-xs text-emerald-700">
          <CheckCircle2 className="h-3.5 w-3.5" />
          Text read and indexed ({data.chunks_created} searchable section{data.chunks_created === 1 ? "" : "s"}).
        </p>
      )}
      {data.status === "FAILED" && (
        <div className="flex flex-col gap-2">
          <p className="flex items-start gap-1.5 text-xs text-destructive">
            <XCircle className="mt-px h-3.5 w-3.5 shrink-0" />
            {data.error_message ?? "Processing failed."}
          </p>
          {onRetry && (
            <Button size="sm" variant="outline" className="self-start" onClick={onRetry}>
              Try again
            </Button>
          )}
        </div>
      )}
      {data.status === "NEEDS_REVIEW" && (
        <p className="flex items-start gap-1.5 text-xs text-amber-700">
          <TriangleAlert className="mt-px h-3.5 w-3.5 shrink-0" />
          {data.error_message ?? "This image needs review before it can be searched."}
        </p>
      )}
      {ready && data.error_message && <p className="text-xs text-amber-700">{data.error_message}</p>}

      <dl className="grid grid-cols-2 gap-y-1 text-xs text-muted-foreground">
        <dt>Patient</dt>
        <dd className="text-foreground">{data.patient_id ?? "Not identified yet"}</dd>
        {data.ocr_quality && (
          <>
            <dt>Text quality</dt>
            <dd className="text-foreground">
              {data.ocr_quality}
              {data.ocr_mean_confidence !== null && ` (${Math.round(data.ocr_mean_confidence * 100)}% confidence)`}
            </dd>
          </>
        )}
        <dt>Uploaded by</dt>
        <dd className="text-foreground">{data.uploaded_by ?? "—"}</dd>
      </dl>

      {needsPatientConfirmation && (
        <div className="flex flex-col gap-1.5 rounded-md border bg-muted/40 p-2">
          <label htmlFor="confirm-patient" className="text-xs font-medium">
            Confirm which patient this image belongs to
          </label>
          <div className="flex gap-2">
            <select
              id="confirm-patient"
              value={confirmPatient}
              onChange={(e) => setConfirmPatient(e.target.value)}
              className="h-8 flex-1 rounded-md border bg-background px-2 text-xs"
            >
              <option value="">Select a patient...</option>
              {patients.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
            <Button size="sm" disabled={!confirmPatient || confirming} onClick={() => void confirm()}>
              {confirming ? "Confirming..." : "Confirm"}
            </Button>
          </div>
          {confirmError && <p className="text-xs text-destructive">{confirmError}</p>}
        </div>
      )}

      {ocr && text && (
        <div className="flex flex-col gap-1">
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Extracted text</p>
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded border bg-muted/30 p-2 text-xs" data-testid="ocr-text-preview">
            {previewText}
            {!showFullText && text.length > PREVIEW_CHARS && "…"}
          </pre>
          {text.length > PREVIEW_CHARS && (
            <button type="button" className="self-start text-[11px] text-muted-foreground underline" onClick={() => setShowFullText((v) => !v)}>
              {showFullText ? "Show less" : "Show all extracted text"}
            </button>
          )}
        </div>
      )}

      {ready && (
        <Button size="sm" className="self-start" onClick={() => onAsk(data)}>
          Ask about this image
        </Button>
      )}
    </div>
  );
}
