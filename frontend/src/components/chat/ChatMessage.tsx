import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Badge } from "@/components/ui/badge";
import type { Citation, RagStatus } from "@/types";

interface ChatMessageProps {
  role: "user" | "assistant";
  text: string;
  status?: RagStatus;
  citations?: Citation[];
  onCitationClick?: (citation: Citation) => void;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function citationKind(c: Citation): string {
  const kind = c.section ?? c.source_type.toLowerCase();
  return kind.charAt(0).toUpperCase() + kind.slice(1).replace(/_/g, " ");
}

interface GroupedCitation {
  ids: string[];
  label: string;
  // The representative citation this group's click should open — always
  // PDF-backed (document_id set) when the group itself came from a file,
  // since only those are actually openable in the viewer.
  citation: Citation;
}

// Several sources from the same record type on the same date (e.g. five
// vitals read off one observation date) collapse into one line rather than
// five identical-looking rows — detail is still in each source_id's own
// badge (section 45 "source grouping").
function groupCitations(citations: Citation[]): GroupedCitation[] {
  const groups = new Map<
    string,
    { ids: string[]; kind: string; date: string | null; patientId: string | null; fileName: string | null; page: number | null; citation: Citation }
  >();
  for (const c of citations) {
    if (c.file_name) {
      const key = `file:${c.file_name}:${c.page ?? ""}:${c.section ?? ""}`;
      const existing = groups.get(key);
      if (existing) existing.ids.push(c.source_id);
      else groups.set(key, { ids: [c.source_id], kind: citationKind(c), date: null, patientId: null, fileName: c.file_name, page: c.page, citation: c });
      continue;
    }
    const key = `db:${c.section ?? c.source_type}:${c.date ?? ""}:${c.patient_id ?? ""}`;
    const existing = groups.get(key);
    if (existing) existing.ids.push(c.source_id);
    else groups.set(key, { ids: [c.source_id], kind: citationKind(c), date: c.date, patientId: c.patient_id, fileName: null, page: null, citation: c });
  }

  return Array.from(groups.values()).map((g) => {
    const kind = g.ids.length > 1 ? `${g.kind}s` : g.kind;
    if (g.fileName) {
      // An image has no pages: label it as what it is (a "Page 1" would read
      // like a PDF page) and flag a low-confidence scan up front.
      if (g.citation.source_type === "OCR_IMAGE") {
        const lowConfidence = g.citation.ocr_confidence !== null && g.citation.ocr_confidence < 0.85;
        return {
          ids: g.ids,
          label: `${g.fileName} — OCR image${lowConfidence ? " (low OCR confidence)" : ""}`,
          citation: g.citation,
        };
      }
      return { ids: g.ids, label: `${g.fileName}${g.page ? ` — Page ${g.page}` : ""}`, citation: g.citation };
    }
    // "Condition record · P001 · 14 Mar 2026" — patient id included since a
    // summary/multi-patient answer can mix sources from more than one.
    const parts = [`${kind} record`, g.patientId, g.date ? formatDate(g.date) : null].filter(Boolean);
    return { ids: g.ids, label: parts.join(" · "), citation: g.citation };
  });
}

export default function ChatMessage({ role, text, status, citations, onCitationClick }: ChatMessageProps) {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">{text}</div>
      </div>
    );
  }

  const isRestricted = status === "DENIED";
  const isEmpty = status === "NO_AUTHORIZED_CONTEXT";
  const needsClarification = status === "NEEDS_CLARIFICATION";
  const grouped = citations && citations.length > 0 ? groupCitations(citations) : [];

  return (
    <div className="flex flex-col gap-2.5 md:max-w-[85%]">
      <div
        className={
          isRestricted
            ? "rounded-lg border border-destructive/30 bg-destructive/5 px-3.5 py-2.5 text-sm"
            : isEmpty || needsClarification
              ? "rounded-lg border bg-muted/50 px-3.5 py-2.5 text-sm text-muted-foreground"
              : "rounded-lg border bg-card px-3.5 py-2.5 text-sm"
        }
      >
        {isRestricted && <p className="mb-1 text-xs font-semibold uppercase text-destructive">Access restricted</p>}
        {isEmpty && <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">No authorized information found</p>}
        {needsClarification && <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Select a patient</p>}
        <div className="prose-chat">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      </div>

      {grouped.length > 0 && (
        <div className="px-1">
          <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Sources</p>
          <ul className="flex flex-col gap-1">
            {grouped.map((g) => {
              const openable = Boolean(onCitationClick && g.citation.document_id);
              const content = (
                <>
                  <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
                    {g.ids.map((id) => id.replace("SOURCE_", "")).join(",")}
                  </Badge>
                  {g.label}
                </>
              );
              return (
                <li key={g.ids.join(",")}>
                  {openable ? (
                    <button
                      type="button"
                      onClick={() => onCitationClick?.(g.citation)}
                      className="flex items-center gap-2 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                    >
                      {content}
                    </button>
                  ) : (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">{content}</div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
