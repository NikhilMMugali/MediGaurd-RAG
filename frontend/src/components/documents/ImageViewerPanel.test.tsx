import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Citation, OcrResponse } from "@/types";

const { getFileMock, getOcrMock } = vi.hoisted(() => ({ getFileMock: vi.fn(), getOcrMock: vi.fn() }));
vi.mock("@/api/documents", () => ({ getDocumentFileBlob: getFileMock, getDocumentOcr: getOcrMock }));
// PdfViewerPanel (imported for shared helpers) pulls in react-pdf, which needs a worker.
vi.mock("react-pdf", () => ({ pdfjs: { GlobalWorkerOptions: {} }, Document: () => null, Page: () => null }));

import ImageViewerPanel from "@/components/documents/ImageViewerPanel";
import SourceViewerPanel from "@/components/documents/SourceViewerPanel";

const OCR: OcrResponse = {
  document_id: "img-1",
  width: 1000,
  height: 500,
  mean_confidence: 0.97,
  quality: "good",
  problem: null,
  text: "",
  lines: [
    { text: "Patient Name: Meera Krishnan", confidence: 0.98, box: [100, 50, 600, 100] },
    { text: "25-OH Vitamin D 18 ng/mL 30 - 100 LOW", confidence: 0.97, box: [100, 200, 800, 250] },
  ],
};

function citation(overrides: Partial<Citation> = {}): Citation {
  return {
    source_id: "SOURCE_1",
    source_type: "OCR_IMAGE",
    record_id: null,
    file_name: "report.png",
    page: null,
    section: "ocr_image",
    date: null,
    patient_id: "P007",
    evidence_text: "Patient: P007\nDocument image 1\n\nPatient Name: Meera Krishnan\n25-OH Vitamin D 18 ng/mL 30 - 100 LOW",
    document_id: "img-1",
    highlight_text: "25-OH Vitamin D 18 ng/mL 30 - 100 LOW",
    ocr_confidence: 0.97,
    ...overrides,
  };
}

beforeEach(() => {
  getFileMock.mockReset().mockResolvedValue(new Blob(["png"], { type: "image/png" }));
  getOcrMock.mockReset().mockResolvedValue(OCR);
  URL.createObjectURL = vi.fn(() => "blob:image");
  URL.revokeObjectURL = vi.fn();
});

describe("ImageViewerPanel", () => {
  it("shows the original image, outlines only the cited line, and positions it from the OCR box", async () => {
    render(<ImageViewerPanel citation={citation()} onClose={() => {}} />);
    expect(await screen.findByAltText(/report\.png/)).toHaveAttribute("src", "blob:image");
    const regions = await screen.findAllByTestId("ocr-region");
    expect(regions).toHaveLength(1);
    // box [100,200,800,250] on a 1000x500 image
    expect(regions[0]).toHaveStyle({ left: "10%", top: "40%", width: "70%", height: "10%" });
    expect(screen.getByText(/region the text was read from is outlined/i)).toBeInTheDocument();
    expect(getFileMock).toHaveBeenCalledWith("img-1");
  });

  it("shows the supporting OCR text without the generated Patient/Document image header", async () => {
    render(<ImageViewerPanel citation={citation()} onClose={() => {}} />);
    await screen.findAllByTestId("ocr-region");
    expect(screen.getAllByText("25-OH Vitamin D 18 ng/mL 30 - 100 LOW").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Document image 1/)).not.toBeInTheDocument();
  });

  it("says region highlighting is unavailable instead of drawing a guess when the lines are not found", async () => {
    render(<ImageViewerPanel citation={citation({ highlight_text: "Cholesterol 200 mg/dL" })} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/highlighting is unavailable/i)).toBeInTheDocument());
    expect(screen.queryByTestId("ocr-region")).not.toBeInTheDocument();
    expect(screen.getByText("Cholesterol 200 mg/dL")).toBeInTheDocument();
  });

  it("still shows the image and text when the OCR boxes cannot be loaded", async () => {
    getOcrMock.mockRejectedValue(new Error("nope"));
    render(<ImageViewerPanel citation={citation()} onClose={() => {}} />);
    expect(await screen.findByAltText(/report\.png/)).toBeInTheDocument();
    expect(screen.queryByTestId("ocr-region")).not.toBeInTheDocument();
    expect(screen.getAllByText("25-OH Vitamin D 18 ng/mL 30 - 100 LOW").length).toBeGreaterThan(0);
  });

  it("warns when OCR confidence is low and stays quiet when it is high", async () => {
    const { unmount } = render(<ImageViewerPanel citation={citation({ ocr_confidence: 0.6 })} onClose={() => {}} />);
    expect(await screen.findByText(/OCR confidence is 60%/)).toBeInTheDocument();
    unmount();
    render(<ImageViewerPanel citation={citation({ ocr_confidence: 0.97 })} onClose={() => {}} />);
    await screen.findByAltText(/report\.png/);
    expect(screen.queryByText(/OCR confidence is/)).not.toBeInTheDocument();
  });

  it("shows an error, not a blank panel, when the image cannot be fetched", async () => {
    getFileMock.mockRejectedValue(new Error("403"));
    render(<ImageViewerPanel citation={citation()} onClose={() => {}} />);
    expect(await screen.findByText(/could not load this image/i)).toBeInTheDocument();
  });

  it("switching citation clears the previous image's boxes", async () => {
    const { rerender } = render(<ImageViewerPanel citation={citation()} onClose={() => {}} />);
    await screen.findAllByTestId("ocr-region");
    getOcrMock.mockResolvedValue({ ...OCR, document_id: "img-2", lines: [{ text: "Other", confidence: 0.9, box: [0, 0, 10, 10] }] });
    rerender(<ImageViewerPanel citation={citation({ document_id: "img-2", source_id: "SOURCE_2", highlight_text: "unrelated" })} onClose={() => {}} />);
    await waitFor(() => expect(screen.queryByTestId("ocr-region")).not.toBeInTheDocument());
  });
});

describe("SourceViewerPanel", () => {
  it("opens the image viewer for an OCR image citation", async () => {
    render(<SourceViewerPanel citation={citation()} onClose={() => {}} />);
    expect(await screen.findByText(/Image · text read by OCR/)).toBeInTheDocument();
  });
  it("renders nothing for a database citation with no document, and never fetches a file", () => {
    const { container } = render(<SourceViewerPanel citation={citation({ document_id: null, source_type: "SYNTHEA" })} onClose={() => {}} />);
    expect(container).toBeEmptyDOMElement();
    expect(getFileMock).not.toHaveBeenCalled();
  });
});
