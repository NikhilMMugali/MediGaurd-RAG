import { Badge } from "@/components/ui/badge";
import type { Citation, RagStatus } from "@/types";

interface ChatMessageProps {
  role: "user" | "assistant";
  text: string;
  status?: RagStatus;
  citations?: Citation[];
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function citationLabel(c: Citation): string {
  if (c.file_name) return `${c.file_name}${c.page ? ` — Page ${c.page}` : ""}${c.section ? ` — ${c.section}` : ""}`;
  const kind = c.section ?? c.source_type.toLowerCase();
  const label = kind.charAt(0).toUpperCase() + kind.slice(1).replace(/_/g, " ");
  return c.date ? `${label} record · ${formatDate(c.date)}` : `${label} record`;
}

export default function ChatMessage({ role, text, status, citations }: ChatMessageProps) {
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">{text}</div>
      </div>
    );
  }

  const isRestricted = status === "DENIED";
  const isEmpty = status === "NO_AUTHORIZED_CONTEXT";

  return (
    <div className="flex flex-col gap-2">
      <div
        className={
          isRestricted
            ? "max-w-[85%] rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm"
            : isEmpty
              ? "max-w-[85%] rounded-lg border bg-muted/50 px-3 py-2 text-sm text-muted-foreground"
              : "max-w-[85%] rounded-lg border bg-card px-3 py-2 text-sm"
        }
      >
        {isRestricted && <p className="mb-1 text-xs font-semibold uppercase text-destructive">Access restricted</p>}
        {isEmpty && <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">No authorized information found</p>}
        <p className="whitespace-pre-wrap">{text}</p>
      </div>

      {citations && citations.length > 0 && (
        <div className="max-w-[85%] rounded-lg border bg-muted/30 px-3 py-2">
          <p className="mb-1.5 text-xs font-semibold text-muted-foreground">Sources</p>
          <ul className="flex flex-col gap-1">
            {citations.map((c) => (
              <li key={c.source_id} className="flex items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
                  {c.source_id.replace("SOURCE_", "")}
                </Badge>
                {citationLabel(c)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
