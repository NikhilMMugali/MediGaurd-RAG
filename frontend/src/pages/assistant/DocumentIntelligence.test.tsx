import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ user: { username: "doctor01", full_name: "Dr", role: "DOCTOR", department: null } }),
}));
// The page's children are exercised by their own tests; here only the page shell matters.
vi.mock("@/components/documents/DocumentUploader", () => ({ default: () => <p>PDF DROPZONE</p> }));
vi.mock("@/components/documents/ImageUploader", () => ({ default: () => <p>IMAGE DROPZONE</p> }));
vi.mock("@/components/documents/DocumentProcessingStatus", () => ({ default: () => null }));
vi.mock("@/components/documents/ImageProcessingStatus", () => ({ default: () => null }));
vi.mock("@/components/documents/DocumentList", () => ({ default: () => <p>DOCUMENT LIST</p> }));
vi.mock("@/components/documents/DocumentQuestionPanel", () => ({ default: () => <p>QUESTION PANEL</p> }));
vi.mock("@/components/documents/SourceViewerPanel", () => ({ default: () => null }));
vi.mock("@/api/documents", () => ({ uploadImage: vi.fn() }));

import DocumentIntelligence from "@/pages/assistant/DocumentIntelligence";

const panel = (id: string) => document.getElementById(`panel-${id}`) as HTMLElement;

describe("Document Intelligence upload sections", () => {
  it("offers two clearly labelled sections, PDF first and unchanged", () => {
    render(<DocumentIntelligence />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["PDF Upload", "Upload Image using OCR"]);
    expect(screen.getByRole("tab", { name: "PDF Upload" })).toHaveAttribute("aria-selected", "true");
    expect(panel("pdf")).toHaveClass("grid");
    expect(panel("image")).toHaveClass("hidden");
    expect(panel("image")).not.toHaveClass("grid");
  });

  it("switching to the OCR tab shows its title and description and hides the PDF section (and back)", async () => {
    render(<DocumentIntelligence />);
    await userEvent.click(screen.getByRole("tab", { name: "Upload Image using OCR" }));

    expect(screen.getByRole("tab", { name: "Upload Image using OCR" })).toHaveAttribute("aria-selected", "true");
    expect(panel("image")).toHaveClass("grid");
    expect(panel("pdf")).toHaveClass("hidden");
    expect(panel("pdf")).not.toHaveClass("grid");
    expect(screen.getByRole("heading", { name: "Upload Image using OCR" })).toBeInTheDocument();
    expect(screen.getByText(/MediGaurd extracts the visible text and makes it searchable through the secure AI assistant/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "PDF Upload" }));
    expect(panel("pdf")).toHaveClass("grid");
    expect(panel("image")).toHaveClass("hidden");
  });

  it("keeps both uploaders mounted so switching tabs never discards a selection", async () => {
    render(<DocumentIntelligence />);
    await userEvent.click(screen.getByRole("tab", { name: "Upload Image using OCR" }));
    expect(screen.getByText("PDF DROPZONE")).toBeInTheDocument();
    expect(screen.getByText("IMAGE DROPZONE")).toBeInTheDocument();
  });

  it("labels the PDF section as direct text extraction, not OCR", () => {
    render(<DocumentIntelligence />);
    expect(screen.getByText(/extracted directly from the file \(not OCR\)/)).toBeInTheDocument();
  });
});
