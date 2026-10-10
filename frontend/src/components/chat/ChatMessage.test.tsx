import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ChatMessage from "@/components/chat/ChatMessage";
import type { Citation } from "@/types";

function pdfCitation(overrides: Partial<Citation> = {}): Citation {
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
    highlight_text: null,
    ...overrides,
  };
}

function dbCitation(overrides: Partial<Citation> = {}): Citation {
  return {
    source_id: "SOURCE_1",
    source_type: "medication",
    record_id: "med-1",
    file_name: null,
    page: null,
    section: "medication",
    date: "2026-06-30",
    patient_id: "P001",
    evidence_text: null,
    document_id: null,
    highlight_text: null,
    ...overrides,
  };
}

describe("ChatMessage citation handling", () => {
  it("clicking a PDF-backed citation calls onCitationClick with that exact citation", async () => {
    const citation = pdfCitation();
    const onCitationClick = vi.fn();
    render(<ChatMessage role="assistant" text="answer" citations={[citation]} onCitationClick={onCitationClick} />);

    await userEvent.click(screen.getByRole("button", { name: /report\.pdf/ }));

    expect(onCitationClick).toHaveBeenCalledTimes(1);
    expect(onCitationClick).toHaveBeenCalledWith(citation);
  });

  it("a database citation with no document_id renders as non-clickable and never opens a PDF", () => {
    const onCitationClick = vi.fn();
    render(<ChatMessage role="assistant" text="answer" citations={[dbCitation()]} onCitationClick={onCitationClick} />);

    // No button at all for a source with nothing to open — not a disabled
    // button, not a button that silently no-ops on click.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(onCitationClick).not.toHaveBeenCalled();
  });

  it("two citations for two different documents each open their own document, not each other's", async () => {
    const citationA = pdfCitation({ source_id: "SOURCE_1", document_id: "doc-A", file_name: "a.pdf", page: 1 });
    const citationB = pdfCitation({ source_id: "SOURCE_2", document_id: "doc-B", file_name: "b.pdf", page: 7 });
    const onCitationClick = vi.fn();
    render(
      <ChatMessage role="assistant" text="answer" citations={[citationA, citationB]} onCitationClick={onCitationClick} />
    );

    await userEvent.click(screen.getByRole("button", { name: /a\.pdf/ }));
    expect(onCitationClick).toHaveBeenLastCalledWith(citationA);

    await userEvent.click(screen.getByRole("button", { name: /b\.pdf/ }));
    expect(onCitationClick).toHaveBeenLastCalledWith(citationB);
  });

  it("a mix of PDF and database citations in the same answer handles each according to its own type", () => {
    const onCitationClick = vi.fn();
    render(
      <ChatMessage
        role="assistant"
        text="answer"
        citations={[pdfCitation({ source_id: "SOURCE_1" }), dbCitation({ source_id: "SOURCE_2" })]}
        onCitationClick={onCitationClick}
      />
    );

    // Exactly one openable source (the PDF one) — the DB-only source must
    // not also render as a clickable PDF link.
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("a clarification renders a 'Select a patient' notice, not the 'No authorized information' heading", () => {
    render(
      <ChatMessage
        role="assistant"
        text="This question refers to a specific patient, but no patient is selected."
        status="NEEDS_CLARIFICATION"
        citations={[]}
      />
    );
    expect(screen.getByText("Select a patient")).toBeInTheDocument();
    expect(screen.queryByText(/no authorized information found/i)).not.toBeInTheDocument();
    expect(screen.getByText(/no patient is selected/i)).toBeInTheDocument();
  });
});
