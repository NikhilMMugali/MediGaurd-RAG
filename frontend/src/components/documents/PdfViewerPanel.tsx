import * as React from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import { ChevronLeft, ChevronRight, X, ZoomIn, ZoomOut } from "lucide-react";
import { getDocumentFileBlob } from "@/api/documents";
import { ApiError } from "@/api/client";
import type { Citation } from "@/types";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/common/StateViews";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

// A whole-page narrative knowledge record's evidence_text IS that page's
// full text — highlighting "the whole page" is technically correct but not
// a useful visual cue, so highlighting is only attempted for shorter,
// focused evidence snippets (e.g. a single structured fact). Longer
// evidence still opens the right page and shows the full supporting text in
// the panel below — the explicit fallback section 10D allows for when a
// reliable/useful highlight isn't possible.
const MAX_HIGHLIGHT_EVIDENCE_CHARS = 500;

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildTextRenderer(evidenceText: string | null): ((item: { str: string }) => string) | undefined {
  if (!evidenceText || evidenceText.length > MAX_HIGHLIGHT_EVIDENCE_CHARS) return undefined;
  const normalizedEvidence = evidenceText.replace(/\s+/g, " ").toLowerCase();
  return (textItem: { str: string }) => {
    const fragment = textItem.str.trim();
    if (fragment.length < 3) return escapeHtml(textItem.str);
    const normalizedFragment = fragment.replace(/\s+/g, " ").toLowerCase();
    if (normalizedEvidence.includes(normalizedFragment)) {
      return `<mark class="pdf-evidence-highlight">${escapeHtml(textItem.str)}</mark>`;
    }
    return escapeHtml(textItem.str);
  };
}

interface PdfViewerPanelProps {
  citation: Citation | null;
  onClose: () => void;
}

export default function PdfViewerPanel({ citation, onClose }: PdfViewerPanelProps) {
  const [blobUrl, setBlobUrl] = React.useState<string | null>(null);
  const [numPages, setNumPages] = React.useState<number | null>(null);
  const [pageNumber, setPageNumber] = React.useState(1);
  const [scale, setScale] = React.useState(1.1);
  const [error, setError] = React.useState<string | null>(null);

  const documentId = citation?.document_id ?? null;

  React.useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setBlobUrl(null);
    setNumPages(null);
    setError(null);

    if (!documentId) return;

    getDocumentFileBlob(documentId)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load this document.");
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId]);

  React.useEffect(() => {
    if (citation?.page) setPageNumber(citation.page);
  }, [citation?.page, documentId]);

  const textRenderer = React.useMemo(() => buildTextRenderer(citation?.evidence_text ?? null), [citation?.evidence_text]);
  const highlightSkipped = Boolean(citation?.evidence_text && citation.evidence_text.length > MAX_HIGHLIGHT_EVIDENCE_CHARS);

  if (!citation || !documentId) return null;

  return (
    <div className="flex h-full w-full flex-col border-l bg-card">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2.5">
        <p className="truncate text-sm font-medium">{citation.file_name ?? "Source document"}</p>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onClose} aria-label="Close document viewer">
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex items-center justify-between gap-2 border-b px-3 py-1.5">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            disabled={pageNumber <= 1}
            onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[70px] text-center text-xs text-muted-foreground">
            {numPages ? `Page ${pageNumber} / ${numPages}` : "—"}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            disabled={!numPages || pageNumber >= numPages}
            onClick={() => setPageNumber((p) => Math.min(numPages ?? p, p + 1))}
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setScale((s) => Math.max(0.6, s - 0.15))} aria-label="Zoom out">
            <ZoomOut className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setScale((s) => Math.min(2.2, s + 0.15))} aria-label="Zoom in">
            <ZoomIn className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-muted/30 p-3">
        {error && <p className="p-4 text-sm text-destructive">{error}</p>}
        {!error && !blobUrl && <LoadingState label="Loading document..." />}
        {!error && blobUrl && (
          <Document file={blobUrl} onLoadSuccess={({ numPages: n }) => setNumPages(n)} loading={<LoadingState label="Rendering PDF..." />}>
            <Page pageNumber={pageNumber} scale={scale} customTextRenderer={textRenderer} />
          </Document>
        )}
      </div>

      <div className="border-t p-3">
        <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Supporting evidence</p>
        {citation.evidence_text ? (
          <p className="max-h-28 overflow-y-auto whitespace-pre-wrap text-xs text-foreground">{citation.evidence_text}</p>
        ) : (
          <p className="text-xs text-muted-foreground">No extracted text is available for this source.</p>
        )}
        {highlightSkipped && (
          <p className="mt-1 text-[11px] text-muted-foreground">
            This citation covers the whole page, so no specific passage is highlighted above.
          </p>
        )}
      </div>
    </div>
  );
}
