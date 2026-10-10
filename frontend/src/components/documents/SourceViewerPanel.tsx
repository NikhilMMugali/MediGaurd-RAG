import type { Citation } from "@/types";
import PdfViewerPanel from "@/components/documents/PdfViewerPanel";
import ImageViewerPanel from "@/components/documents/ImageViewerPanel";

// One entry point for "open this citation's source". The type comes from the
// server-validated citation (never from the model's text): an OCR image opens
// in the image viewer, everything with a document opens in the PDF viewer, and
// a database-only citation (no document_id) opens nothing at all.
export default function SourceViewerPanel({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
  if (!citation || !citation.document_id) return null;
  return citation.source_type === "OCR_IMAGE" ? (
    <ImageViewerPanel citation={citation} onClose={onClose} />
  ) : (
    <PdfViewerPanel citation={citation} onClose={onClose} />
  );
}
