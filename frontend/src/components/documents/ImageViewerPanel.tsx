import * as React from "react";
import { ExternalLink, TriangleAlert } from "lucide-react";
import { getDocumentFileBlob, getDocumentOcr } from "@/api/documents";
import { ApiError } from "@/api/client";
import type { Citation, OcrResponse } from "@/types";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/common/StateViews";
import ErrorBoundary from "@/components/common/ErrorBoundary";
import { ViewerFrame, openOriginalInNewTab, stripSyntheticHeader } from "@/components/documents/PdfViewerPanel";
import { matchOcrLines } from "@/components/documents/ocrHighlight";

// Below this the OCR text may contain misread characters worth double-checking
// against the picture (the engine's own scale: 1 = certain).
const LOW_CONFIDENCE = 0.85;

function ImageViewerInner({ citation, onClose }: { citation: Citation; onClose: () => void }) {
  const documentId = citation.document_id as string;
  const [imageUrl, setImageUrl] = React.useState<string | null>(null);
  const [ocr, setOcr] = React.useState<OcrResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setImageUrl(null);
    setOcr(null);
    setError(null);

    getDocumentFileBlob(documentId)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setImageUrl(objectUrl);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load this image.");
      });
    // The boxes are an enhancement: if they can't be loaded the image and the
    // cited text still show, with the limitation stated.
    getDocumentOcr(documentId)
      .then((data) => {
        if (!cancelled) setOcr(data);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId]);

  const matched = React.useMemo(() => (ocr ? matchOcrLines(ocr.lines, citation.highlight_text) : []), [ocr, citation.highlight_text]);

  const fullText = stripSyntheticHeader(citation.evidence_text);
  const supporting = citation.highlight_text ?? fullText;
  const lowConfidence = citation.ocr_confidence !== null && citation.ocr_confidence < LOW_CONFIDENCE;

  const regionNote = !citation.highlight_text
    ? "No specific passage was selected for this source, so no region is highlighted."
    : !ocr
      ? null
      : matched.length > 0
        ? "The region the text was read from is outlined on the image."
        : "Region-level highlighting is unavailable for this source (the cited lines could not be located in the OCR output), so the supporting text is shown below instead.";

  return (
    <ViewerFrame title={citation.file_name ?? "Source image"} onClose={onClose}>
      <div className="flex items-center justify-between gap-2 border-b px-3 py-1.5">
        <span className="text-xs text-muted-foreground">Image · text read by OCR</span>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => void openOriginalInNewTab(documentId)}
          aria-label="Open original image in a new tab"
        >
          <ExternalLink className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-auto bg-muted/30 p-3">
        {error && <p className="p-4 text-sm text-destructive">{error}</p>}
        {!error && !imageUrl && <LoadingState label="Loading image..." />}
        {!error && imageUrl && (
          <div className="relative inline-block max-w-full">
            <img
              src={imageUrl}
              alt={`Uploaded image ${citation.file_name ?? ""}`.trim()}
              className="block h-auto max-w-full rounded border bg-white"
              onError={() => setError("This image could not be displayed.")}
            />
            {ocr &&
              matched.map((lineIndex) => {
                const [x1, y1, x2, y2] = ocr.lines[lineIndex].box;
                return (
                  <div
                    key={lineIndex}
                    data-testid="ocr-region"
                    className="pointer-events-none absolute rounded-sm border-2 border-amber-500 bg-amber-300/30"
                    style={{
                      left: `${(x1 / ocr.width) * 100}%`,
                      top: `${(y1 / ocr.height) * 100}%`,
                      width: `${((x2 - x1) / ocr.width) * 100}%`,
                      height: `${((y2 - y1) / ocr.height) * 100}%`,
                    }}
                  />
                );
              })}
          </div>
        )}
      </div>

      <div className="border-t p-3">
        <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Supporting evidence (OCR text)</p>
        {supporting ? (
          <p className="max-h-28 overflow-y-auto whitespace-pre-wrap text-xs text-foreground">{supporting}</p>
        ) : (
          <p className="text-xs text-muted-foreground">No extracted text is available for this source.</p>
        )}
        {regionNote && <p className="mt-1 text-[11px] text-muted-foreground">{regionNote}</p>}
        {lowConfidence && (
          <p className="mt-1.5 flex items-start gap-1 text-[11px] text-amber-700">
            <TriangleAlert className="mt-px h-3 w-3 shrink-0" />
            OCR confidence is {Math.round((citation.ocr_confidence ?? 0) * 100)}% for this image — verify important values against the picture.
          </p>
        )}
        {citation.highlight_text && fullText && fullText !== citation.highlight_text && (
          <details className="mt-1.5">
            <summary className="cursor-pointer text-[11px] text-muted-foreground">Full extracted text of this section</summary>
            <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap text-[11px] text-muted-foreground">{fullText}</p>
          </details>
        )}
      </div>
    </ViewerFrame>
  );
}

export default function ImageViewerPanel({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
  if (!citation || !citation.document_id) return null;
  return (
    <ErrorBoundary
      resetKey={`${citation.document_id}:${citation.source_id}`}
      fallback={(_error, reset) => (
        <ViewerFrame title={citation.file_name ?? "Source image"} onClose={onClose}>
          <div className="flex flex-1 flex-col gap-3 p-4 text-sm">
            <p className="text-destructive">This image could not be displayed in the viewer.</p>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={reset}>
                Try again
              </Button>
              <Button size="sm" variant="outline" onClick={() => void openOriginalInNewTab(citation.document_id as string)}>
                Open original image
              </Button>
            </div>
            {citation.highlight_text && <p className="whitespace-pre-wrap text-xs">{citation.highlight_text}</p>}
          </div>
        </ViewerFrame>
      )}
    >
      <ImageViewerInner citation={citation} onClose={onClose} />
    </ErrorBoundary>
  );
}
