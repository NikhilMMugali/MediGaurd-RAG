import * as React from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import { ChevronLeft, ChevronRight, ExternalLink, X, ZoomIn, ZoomOut } from "lucide-react";
import { getDocumentFileBlob } from "@/api/documents";
import { ApiError } from "@/api/client";
import type { Citation } from "@/types";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/common/StateViews";
import ErrorBoundary from "@/components/common/ErrorBoundary";
import { locateHighlightItems } from "@/components/documents/highlight";

// The "legacy" pdf.js build (aliased in vite.config.ts) targets older
// browsers; the worker is wrapped (src/pdf/pdfWorker.ts) so a
// Promise.withResolvers polyfill is installed inside the worker too. The
// standard build threw on older Safari/Chromium, which — with no error
// boundary — blanked the whole app when a citation was clicked.
let pdfWorkerReady = false;
// Created lazily, on the first PDF open, rather than on every app load.
function ensurePdfWorker() {
  if (pdfWorkerReady || typeof Worker === "undefined") return;
  pdfjs.GlobalWorkerOptions.workerPort = new Worker(new URL("../../pdf/pdfWorker.ts", import.meta.url), { type: "module" });
  pdfWorkerReady = true;
}

// Fallback only, for citations that arrive without highlight_text: a short
// evidence snippet can still be located on the page; a whole-page chunk
// can't be usefully highlighted.
const MAX_FALLBACK_HIGHLIGHT_CHARS = 500;

// The knowledge generator prepends these lines to each page chunk. They are
// not printed in the PDF, so they are never shown as evidence and never used
// for matching.
const SYNTHETIC_HEADER_LINE = /^(patient:|document (page|image) \d+)/i;

export function stripSyntheticHeader(text: string | null): string | null {
  if (!text) return null;
  const cleaned = text
    .split("\n")
    .filter((line) => !SYNTHETIC_HEADER_LINE.test(line.trim()))
    .join("\n")
    .trim();
  return cleaned || null;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

const MIN_ZOOM = 0.6;
const MAX_ZOOM = 2.5;
const PAGE_PADDING_PX = 24;

type HighlightStatus = "none" | "pending" | "found" | "not-found";

interface PdfViewerPanelProps {
  citation: Citation | null;
  onClose: () => void;
}

export async function openOriginalInNewTab(documentId: string) {
  // Opened synchronously so popup blockers allow it, then pointed at the
  // authenticated blob once the file arrives (a plain link couldn't carry
  // the Authorization header).
  const tab = window.open("", "_blank");
  try {
    const blob = await getDocumentFileBlob(documentId);
    const url = URL.createObjectURL(blob);
    if (tab) tab.location.href = url;
    else window.open(url, "_blank");
  } catch {
    tab?.close();
  }
}

export function ViewerFrame({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="flex h-full w-full flex-col border-l bg-card">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2.5">
        <p className="truncate text-sm font-medium">{title}</p>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onClose} aria-label="Close document viewer">
          <X className="h-4 w-4" />
        </Button>
      </div>
      {children}
    </div>
  );
}

function EvidenceBlock({ citation, status }: { citation: Citation; status: HighlightStatus }) {
  const fullPage = stripSyntheticHeader(citation.evidence_text);
  const supporting = citation.highlight_text ?? fullPage;
  return (
    <div className="border-t p-3">
      <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Supporting evidence</p>
      {supporting ? (
        <p className="max-h-28 overflow-y-auto whitespace-pre-wrap text-xs text-foreground">{supporting}</p>
      ) : (
        <p className="text-xs text-muted-foreground">No extracted text is available for this source.</p>
      )}
      {status === "found" && <p className="mt-1 text-[11px] text-muted-foreground">Highlighted on the page above.</p>}
      {status === "not-found" && (
        <p className="mt-1 text-[11px] text-muted-foreground">
          This passage could not be located in the page's text layer, so nothing is highlighted — the page shown is still the cited one.
        </p>
      )}
      {citation.highlight_text && fullPage && fullPage !== citation.highlight_text && (
        <details className="mt-1.5">
          <summary className="cursor-pointer text-[11px] text-muted-foreground">Full extracted page text</summary>
          <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap text-[11px] text-muted-foreground">{fullPage}</p>
        </details>
      )}
    </div>
  );
}

function PdfViewerPanelInner({ citation, onClose }: { citation: Citation; onClose: () => void }) {
  const [blobUrl, setBlobUrl] = React.useState<string | null>(null);
  const [numPages, setNumPages] = React.useState<number | null>(null);
  const [pageNumber, setPageNumber] = React.useState(1);
  const [zoom, setZoom] = React.useState(1);
  const [containerWidth, setContainerWidth] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);
  const [textItems, setTextItems] = React.useState<{ pageKey: string; strings: string[] } | null>(null);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  const documentId = citation.document_id;

  React.useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setBlobUrl(null);
    setNumPages(null);
    setError(null);
    setTextItems(null);

    if (!documentId) return;

    getDocumentFileBlob(documentId)
      .then((blob) => {
        if (cancelled) return;
        ensurePdfWorker();
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
    // A structured-answer citation can carry a real document_id with
    // page=None. Without an unconditional set, clicking it right after a
    // paged citation would leave the previous document's page number in
    // place. 1 is the correct "no specific page cited" default.
    setPageNumber(citation.page ?? 1);
    setTextItems(null);
  }, [citation.page, documentId]);

  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const update = () => setContainerWidth(el.clientWidth);
    update();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [documentId, blobUrl]);

  // A page number past the end of the document (or below 1) is clamped
  // rather than handed to pdf.js, which would reject it.
  const shownPage = numPages ? Math.min(Math.max(1, pageNumber), numPages) : Math.max(1, pageNumber);
  const pageKey = `${documentId}:${shownPage}`;

  const highlightSource = React.useMemo(() => {
    if (citation.highlight_text) return citation.highlight_text;
    const fallback = stripSyntheticHeader(citation.evidence_text);
    return fallback && fallback.length <= MAX_FALLBACK_HIGHLIGHT_CHARS ? fallback : null;
  }, [citation.highlight_text, citation.evidence_text]);

  const highlighted = React.useMemo(
    () => (textItems && textItems.pageKey === pageKey ? locateHighlightItems(textItems.strings, highlightSource) : new Set<number>()),
    [textItems, pageKey, highlightSource],
  );

  const status: HighlightStatus = !highlightSource
    ? "none"
    : !textItems || textItems.pageKey !== pageKey
      ? "pending"
      : highlighted.size > 0
        ? "found"
        : "not-found";

  const textRenderer = React.useMemo(() => {
    if (highlighted.size === 0) return undefined;
    return ({ str, itemIndex }: { str: string; itemIndex: number }) =>
      highlighted.has(itemIndex) ? `<mark class="pdf-evidence-highlight">${escapeHtml(str)}</mark>` : escapeHtml(str);
  }, [highlighted]);

  // Scrolls only the viewer's own scroll container. element.scrollIntoView
  // would also scroll every overflow:hidden ancestor, which can shove the
  // whole app layout out of view.
  const scrollHighlightIntoView = React.useCallback(() => {
    const container = scrollRef.current;
    const mark = container?.querySelector("mark.pdf-evidence-highlight");
    if (!container || !mark) return;
    const containerBox = container.getBoundingClientRect();
    const markBox = mark.getBoundingClientRect();
    container.scrollTo({ top: container.scrollTop + (markBox.top - containerBox.top) - containerBox.height / 3, behavior: "smooth" });
  }, []);

  const pageWidth = containerWidth > 0 ? Math.max(240, Math.floor((containerWidth - PAGE_PADDING_PX) * zoom)) : undefined;

  return (
    <ViewerFrame title={citation.file_name ?? "Source document"} onClose={onClose}>
      <div className="flex items-center justify-between gap-2 border-b px-3 py-1.5">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            disabled={shownPage <= 1}
            onClick={() => setPageNumber(Math.max(1, shownPage - 1))}
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[70px] text-center text-xs text-muted-foreground">{numPages ? `Page ${shownPage} / ${numPages}` : "—"}</span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            disabled={!numPages || shownPage >= numPages}
            onClick={() => setPageNumber(Math.min(numPages ?? shownPage, shownPage + 1))}
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setZoom((z) => Math.max(MIN_ZOOM, z - 0.2))} aria-label="Zoom out">
            <ZoomOut className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setZoom((z) => Math.min(MAX_ZOOM, z + 0.2))} aria-label="Zoom in">
            <ZoomIn className="h-4 w-4" />
          </Button>
          {documentId && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => void openOriginalInNewTab(documentId)}
              aria-label="Open original PDF in a new tab"
            >
              <ExternalLink className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-auto bg-muted/30 p-3">
        {error && <p className="p-4 text-sm text-destructive">{error}</p>}
        {!error && !blobUrl && <LoadingState label="Loading document..." />}
        {!error && blobUrl && (
          <Document
            file={blobUrl}
            suspense={false}
            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
            onLoadError={() => setError("This file could not be opened as a PDF.")}
            onSourceError={() => setError("This file could not be read.")}
            loading={<LoadingState label="Rendering PDF..." />}
            error={<p className="p-4 text-sm text-destructive">This file could not be opened as a PDF.</p>}
          >
            <Page
              pageNumber={shownPage}
              width={pageWidth}
              customTextRenderer={textRenderer}
              renderAnnotationLayer={false}
              onGetTextSuccess={(content) =>
                setTextItems({
                  pageKey,
                  strings: content.items.map((item) => ("str" in item ? item.str : "")),
                })
              }
              onRenderTextLayerSuccess={scrollHighlightIntoView}
            />
          </Document>
        )}
      </div>

      <EvidenceBlock citation={citation} status={status} />
    </ViewerFrame>
  );
}

export default function PdfViewerPanel({ citation, onClose }: PdfViewerPanelProps) {
  if (!citation || !citation.document_id) return null;
  const resetKey = `${citation.document_id}:${citation.page ?? ""}:${citation.source_id}`;

  return (
    <ErrorBoundary
      resetKey={resetKey}
      fallback={(_error, reset) => (
        <ViewerFrame title={citation.file_name ?? "Source document"} onClose={onClose}>
          <div className="flex flex-1 flex-col gap-3 overflow-auto p-4 text-sm">
            <p className="text-destructive">This PDF could not be displayed in the viewer (your browser may not support it).</p>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={reset}>
                Try again
              </Button>
              <Button size="sm" variant="outline" onClick={() => void openOriginalInNewTab(citation.document_id as string)}>
                Open original PDF
              </Button>
            </div>
          </div>
          <EvidenceBlock citation={citation} status="none" />
        </ViewerFrame>
      )}
    >
      <PdfViewerPanelInner citation={citation} onClose={onClose} />
    </ErrorBoundary>
  );
}
