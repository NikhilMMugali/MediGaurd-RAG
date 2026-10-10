import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Citation } from "@/types";

const { getDocumentFileBlobMock } = vi.hoisted(() => ({ getDocumentFileBlobMock: vi.fn() }));

vi.mock("@/api/documents", () => ({
  getDocumentFileBlob: getDocumentFileBlobMock,
}));

// react-pdf's real Document/Page need a worker and an actual PDF byte
// stream — not available in jsdom. Stubbed with simple components that
// expose exactly the props PdfViewerPanel passes them, which is the
// property these tests actually verify (correct file/page, not react-pdf's
// own rendering).
vi.mock("react-pdf", () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({ file, children }: { file: string; children: React.ReactNode }) => (
    <div data-testid="pdf-document" data-file={file}>
      {children}
    </div>
  ),
  Page: ({ pageNumber }: { pageNumber: number }) => <div data-testid="pdf-page">{pageNumber}</div>,
}));

import PdfViewerPanel from "@/components/documents/PdfViewerPanel";

function citation(overrides: Partial<Citation> = {}): Citation {
  return {
    source_id: "SOURCE_1",
    source_type: "UPLOADED_PDF",
    record_id: null,
    file_name: "report.pdf",
    page: 3,
    section: "document",
    date: null,
    patient_id: "P105",
    evidence_text: "25-OH Vitamin D: 18 ng/mL",
    document_id: "doc-105",
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// jsdom doesn't implement createObjectURL/revokeObjectURL at all — patched
// directly on the real URL object (rather than vi.stubGlobal-swapping the
// whole class) so there's no hook-ordering race with
// @testing-library/react's own auto-registered unmount cleanup, which also
// runs in an afterEach and calls this component's cleanup effect.
beforeEach(() => {
  getDocumentFileBlobMock.mockReset();
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
});

describe("PdfViewerPanel", () => {
  it("requests the cited document and renders the cited page once loaded", async () => {
    const blob = new Blob(["%PDF"], { type: "application/pdf" });
    getDocumentFileBlobMock.mockResolvedValue(blob);

    render(<PdfViewerPanel citation={citation({ document_id: "doc-105", page: 3 })} onClose={() => {}} />);

    expect(getDocumentFileBlobMock).toHaveBeenCalledWith("doc-105");
    await waitFor(() => expect(screen.getByTestId("pdf-document")).toBeInTheDocument());
    expect(screen.getByTestId("pdf-page")).toHaveTextContent("3");
  });

  it("a page-less citation (structured answer) opens at page 1, not a stale page from nothing", async () => {
    getDocumentFileBlobMock.mockResolvedValue(new Blob(["%PDF"]));
    render(<PdfViewerPanel citation={citation({ document_id: "doc-A", page: null })} onClose={() => {}} />);

    await waitFor(() => expect(screen.getByTestId("pdf-page")).toHaveTextContent("1"));
  });

  it("switching from a paged citation to a page-less citation on a different document does not retain the old page", async () => {
    getDocumentFileBlobMock.mockResolvedValue(new Blob(["%PDF"]));
    const { rerender } = render(
      <PdfViewerPanel citation={citation({ document_id: "doc-A", page: 5 })} onClose={() => {}} />
    );
    await waitFor(() => expect(screen.getByTestId("pdf-page")).toHaveTextContent("5"));

    // A structured-answer citation for a different document, with no page
    // at all. Before the fix, this stayed on page 5 (doc-A's page),
    // visibly wrong for doc-B.
    rerender(<PdfViewerPanel citation={citation({ document_id: "doc-B", page: null })} onClose={() => {}} />);

    await waitFor(() => expect(screen.getByTestId("pdf-page")).toHaveTextContent("1"));
  });

  it("switching documents clears the previous citation's evidence text from the panel", async () => {
    getDocumentFileBlobMock.mockResolvedValue(new Blob(["%PDF"]));
    const { rerender } = render(
      <PdfViewerPanel citation={citation({ document_id: "doc-A", evidence_text: "Evidence about doc A" })} onClose={() => {}} />
    );
    await screen.findByText("Evidence about doc A");

    rerender(
      <PdfViewerPanel citation={citation({ document_id: "doc-B", evidence_text: "Evidence about doc B" })} onClose={() => {}} />
    );

    expect(screen.queryByText("Evidence about doc A")).not.toBeInTheDocument();
    expect(await screen.findByText("Evidence about doc B")).toBeInTheDocument();
  });

  it("shows an error state instead of hanging when the file fetch fails", async () => {
    getDocumentFileBlobMock.mockRejectedValue(new Error("Could not load this document."));
    render(<PdfViewerPanel citation={citation()} onClose={() => {}} />);

    expect(await screen.findByText(/could not load this document/i)).toBeInTheDocument();
    expect(screen.queryByTestId("pdf-document")).not.toBeInTheDocument();
  });

  it("a slow first fetch resolving after a second document was already selected does not overwrite it (no stale overwrite)", async () => {
    const first = deferred<Blob>();
    const second = deferred<Blob>();
    getDocumentFileBlobMock.mockImplementationOnce(() => first.promise).mockImplementationOnce(() => second.promise);

    const { rerender } = render(
      <PdfViewerPanel citation={citation({ document_id: "doc-A" })} onClose={() => {}} />
    );
    // User clicks a second citation (doc-B) before doc-A's fetch resolves.
    rerender(<PdfViewerPanel citation={citation({ document_id: "doc-B" })} onClose={() => {}} />);

    // doc-B's own fetch resolves first (realistic: doc-A's was already in
    // flight and slow).
    second.resolve(new Blob(["%PDF-B"]));
    await waitFor(() => expect(screen.getByTestId("pdf-document")).toBeInTheDocument());

    // doc-A's stale, now-cancelled fetch finally resolves — must not
    // replace the already-correct doc-B content.
    first.resolve(new Blob(["%PDF-A"]));
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.getByTestId("pdf-document")).toBeInTheDocument();
    expect(getDocumentFileBlobMock).toHaveBeenCalledWith("doc-B");
  });
});
