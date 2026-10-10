import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DocumentStatusResponse, OcrResponse } from "@/types";

const { getStatusMock, getOcrMock, confirmMock, listPatientsMock } = vi.hoisted(() => ({
  getStatusMock: vi.fn(),
  getOcrMock: vi.fn(),
  confirmMock: vi.fn(),
  listPatientsMock: vi.fn(),
}));
vi.mock("@/api/documents", () => ({ getDocumentStatus: getStatusMock, getDocumentOcr: getOcrMock, confirmImagePatient: confirmMock }));
vi.mock("@/api/patients", () => ({ listAllPatientIds: listPatientsMock }));

import ImageProcessingStatus from "@/components/documents/ImageProcessingStatus";

function status(overrides: Partial<DocumentStatusResponse> = {}): DocumentStatusResponse {
  return {
    document_id: "img-1",
    file_name: "report.png",
    status: "COMPLETED",
    patient_id: "P007",
    uploaded_by: "Dr. Example",
    created_at: "2026-10-10T10:00:00",
    page_count: 1,
    records_created: 0,
    chunks_created: 2,
    error_message: null,
    source_type: "OCR_IMAGE",
    ocr_quality: "good",
    ocr_mean_confidence: 0.97,
    ...overrides,
  };
}
const OCR: OcrResponse = {
  document_id: "img-1", width: 100, height: 100, mean_confidence: 0.97, quality: "good", problem: null,
  text: "LABORATORY REPORT\nHemoglobin 13.8 g/dL", lines: [],
};

beforeEach(() => {
  getStatusMock.mockReset();
  getOcrMock.mockReset().mockResolvedValue(OCR);
  confirmMock.mockReset();
  listPatientsMock.mockReset().mockResolvedValue(["P007", "P008"]);
});

describe("ImageProcessingStatus", () => {
  it("shows the real in-progress stage and offers no question button yet", async () => {
    getStatusMock.mockResolvedValue(status({ status: "OCR_PROCESSING", ocr_quality: null, ocr_mean_confidence: null, patient_id: null, chunks_created: 0 }));
    render(<ImageProcessingStatus documentId="img-1" onAsk={() => {}} />);
    const stages = await screen.findByLabelText("Processing stages");
    expect(stages).toHaveTextContent("Reading text (OCR)");
    expect(screen.getByText("Not identified yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /ask about this image/i })).not.toBeInTheDocument();
  });

  it("when ready: shows patient, quality, the extracted text, and lets the user ask about the image", async () => {
    getStatusMock.mockResolvedValue(status());
    const onAsk = vi.fn();
    render(<ImageProcessingStatus documentId="img-1" onAsk={onAsk} />);
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("P007")).toBeInTheDocument();
    expect(screen.getByText(/good \(97% confidence\)/)).toBeInTheDocument();
    expect(await screen.findByTestId("ocr-text-preview")).toHaveTextContent("Hemoglobin 13.8 g/dL");
    await userEvent.click(screen.getByRole("button", { name: /ask about this image/i }));
    expect(onAsk).toHaveBeenCalledWith(expect.objectContaining({ document_id: "img-1" }));
  });

  it("a low-quality image explains why and offers no patient confirmation (it cannot help)", async () => {
    getStatusMock.mockResolvedValue(
      status({ status: "NEEDS_REVIEW", ocr_quality: "poor", ocr_mean_confidence: 0.3, patient_id: null, chunks_created: 0, error_message: "The text could only be read with low confidence (30%)." }),
    );
    render(<ImageProcessingStatus documentId="img-1" onAsk={() => {}} />);
    expect(await screen.findByText(/low confidence \(30%\)/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/confirm which patient/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /ask about this image/i })).not.toBeInTheDocument();
  });

  it("an unresolved identity can be confirmed, which resumes polling the same document", async () => {
    getStatusMock.mockResolvedValue(status({ status: "NEEDS_REVIEW", patient_id: null, chunks_created: 0, error_message: "The name read from the image is close to an existing patient (P007)." }));
    confirmMock.mockResolvedValue({ document_id: "img-1", file_name: "report.png", status: "MAPPING", message: "", patient_id: "P007", duplicate: false });
    render(<ImageProcessingStatus documentId="img-1" onAsk={() => {}} />);

    const select = await screen.findByLabelText(/confirm which patient/i);
    const confirm = screen.getByRole("button", { name: /^confirm$/i });
    expect(confirm).toBeDisabled();
    await waitFor(() => expect(screen.getByRole("option", { name: "P007" })).toBeInTheDocument());
    await userEvent.selectOptions(select, "P007");
    await userEvent.click(confirm);

    await waitFor(() => expect(confirmMock).toHaveBeenCalledWith("img-1", "P007"));
    await waitFor(() => expect(getStatusMock.mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it("surfaces a confirmation failure instead of silently doing nothing", async () => {
    const { ApiError } = await import("@/api/client");
    getStatusMock.mockResolvedValue(status({ status: "NEEDS_REVIEW", patient_id: null, chunks_created: 0, error_message: "Confirm the patient." }));
    confirmMock.mockRejectedValue(new ApiError(403, "You do not have access to this patient."));
    render(<ImageProcessingStatus documentId="img-1" onAsk={() => {}} />);
    await waitFor(() => expect(screen.getByRole("option", { name: "P008" })).toBeInTheDocument());
    await userEvent.selectOptions(await screen.findByLabelText(/confirm which patient/i), "P008");
    await userEvent.click(screen.getByRole("button", { name: /^confirm$/i }));
    expect(await screen.findByText("You do not have access to this patient.")).toBeInTheDocument();
  });

  it("a failed image shows the reason and a working retry", async () => {
    getStatusMock.mockResolvedValue(status({ status: "FAILED", ocr_quality: null, patient_id: null, chunks_created: 0, error_message: "The OCR engine is not available on this server." }));
    const onRetry = vi.fn();
    render(<ImageProcessingStatus documentId="img-1" onAsk={() => {}} onRetry={onRetry} />);
    expect(await screen.findByText(/OCR engine is not available/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalled();
  });
});
